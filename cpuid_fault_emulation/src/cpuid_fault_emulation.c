#include <linux/init.h>   /* Needed for the macros */
#include <linux/module.h> /* Needed by all modules */
#include <linux/printk.h> /* Needed for pr_info() */
#include <linux/string.h> /* for memset() and memcpy() */
#include <linux/bits.h>
#include <linux/version.h>
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 11, 0)
    #include <linux/cpuhplock.h>
#else
    #include <linux/cpu.h>
#endif
#include <linux/suspend.h>

#include <linux/types.h>
#include <asm/desc.h>
#include <asm/msr.h>
#include <linux/mm.h>

#include <host_state.h>
#include <vmcb_layout.h>

#define MSR_PM_BASE1  0x00000000
#define MSR_PM_BASE2  0xc0000000
#define MSR_PM_BASE3  0xc0010000
#define SVM_MSR_VM_HSAVE_PA 0xc0010117

#define UNLOAD_HV_MAGIC 0x40067420

#define SVM_SUPPORT_LEAF 0x80000001
#define SVM_SUPPORT_BIT 2

#define SVM_MSR_VM_CR 0xc0010114
#define VM_CR_SVMDIS_BIT 4

#define VMEXIT_CPUID   0x72
#define VMEXIT_MSRPROT 0x7C

/* VECTOR 8 bits = 0x0D (GP) */
/* TYPE 3 bits = 0x3 (Fault) */
/* EV 1 bit = 0x1 (Error Code Valid) */
/* reserved 19 bits */
/* V 1 bit = 0x1 (Valid) */
/* ERRORCODE 32 bits = 0x0 */
#define GP0_EVENTINJ (0x0D | (0x3 << 8) | (0x1 << 11) | (0x1 << 31))


#ifndef page_to_phys
#define page_to_phys(page) PFN_PHYS(page_to_pfn(page))
#endif

/* The hypervisor doesn't handle nested virtualization, so attempting to
 * virtualize a kernel currently using virtualization features will probably
 * result in an immediate crash. If you know better you can tell the module
 * to attempt the virtualization anyway */
static int ignore_svm_enabled = 0;
module_param(ignore_svm_enabled, int, 0);

static struct {
	struct page* msrpm_page;
	u64 msrpm_pa;
	bool prev_cpuid_fault_cap;
	bool prev_svm_enabled;
} shared_data;


inline static void vmsave(u64 vmcb_pa) {
	asm volatile ("vmsave" : : "a" (vmcb_pa) : "memory");
}

inline static void vmload(u64 vmcb_pa) {
	asm volatile ("vmload" : : "a" (vmcb_pa) : "memory");
}

inline static void do_cpuid(u32* eax, u32* ebx, u32* ecx, u32* edx) {
	asm volatile ("cpuid"
	             : "+a"(*eax), "=b"(*ebx), "+c"(*ecx), "=d"(*edx)
	             :
	             : "memory");
}

inline static void do_cpuid_leaf(u32 leaf, u32* eax, u32* ebx,
                                 u32* ecx, u32* edx) {
	asm volatile ("cpuid"
	             : "=a"(*eax), "=b"(*ebx), "=c"(*ecx), "=d"(*edx)
	             : "a"(leaf)
	             : "memory");
}

inline static void do_wrmsr(u32 msr, u64 val) {
	asm volatile ("wrmsr" : : "c"(msr), "a"((u32)val), "d" ((u32)(val >> 32)) : "memory");
}

inline static u64 do_rdmsr(u32 msr) {
	u32 low, high;
	asm volatile ("rdmsr" : "=a"(low), "=d" (high) : "c"(msr));
	return low | ((u64)high) << 32;
}

/* Raw writes and reads for cr registers. The kernel has it's own safer
 * versions, however, all the writes we do should use values provided by the
 * kernel, so these consistent raw versions are cleaner to use. */
#define define_cr_ops(cr) \
inline static u64 do_read_ ## cr (void) {\
	u64 val; \
	asm volatile ("movq %%" #cr ", %0" : "=r" (val) : :); \
	return val; \
} \
inline static void do_write_ ## cr (u64 val) {\
	asm volatile ("movq %0, %%" #cr : :"r" (val) :); \
}
define_cr_ops(cr0);
define_cr_ops(cr2);
define_cr_ops(cr3);
define_cr_ops(cr4);

/* Checks the relevant CPUID bits and MSR registers to determine SVM support
 * since the hypervisor doesn't use features like NPT or decode assists,
 * very few checks are needed */
static bool check_svm_support(void) {
	u32 eax, ebx, ecx, edx;

	/* check for "AuthenticAMD" on leaf 0 */
	do_cpuid_leaf(0, &eax, &ebx, &ecx, &edx);
	if (!(ebx == 'htuA' && edx == 'itne' && ecx == 'DMAc'))
		return false;

	/* check for SVM support */
	do_cpuid_leaf(SVM_SUPPORT_LEAF, &eax, &ebx, &ecx, &edx);
	if (!(ecx & (1U << SVM_SUPPORT_BIT)))
		return false;

	/* check if SVM is disabled by the BIOS */
	if (do_rdmsr(SVM_MSR_VM_CR) & BIT_ULL(VM_CR_SVMDIS_BIT))
		return false;

	return true;
}

/* capture_context saves all GPR's, as well as RIP and RFLAGS as they are at
 * it's return, except for RAX, which is saved as 0, but returned as 1 */
noinline_for_stack u64 capture_context(struct InitialContext* registers);

/* run_vm repeatedly runs the VMRUN instruction, effectively continuing to
 * run the guest (the OS), when an intercepted event happens, it calls the
 * handle_vm_exit function with the current state of the guest. If the call
 * returns a non-zero value it begins the process of devirtualizing the 
 * processor */
__attribute__((noreturn)) void run_vm(struct ProcessorStatus* status);

/* called when the guest would execute a CPUID instruction*/
static u64 handle_cpuid(struct ProcessorStatus* status) {
	u32 eax = status->guest_registers.rax;
	u32 ebx;
	u32 ecx = status->guest_registers.rcx;
	u32 edx;
	if(status->vmcb.state_area.cpl == 0) {
		switch (eax) {
		case UNLOAD_HV_MAGIC:
			status->vmcb.state_area.rip += 2;
			return 1; /* tell the hypervisor to devirtualize the processor */
		}
	} else {
		if(status->cpuid_fault) { /* if CPUID should fault */
			status->vmcb.control_area.eventinj = GP0_EVENTINJ; /* inject GP */
			return 0;
		}
	}
	/* otherwise, run CPUID and increase RIP */
	do_cpuid(&eax, &ebx, &ecx, &edx);
	status->guest_registers.rax = eax;
	status->guest_registers.rbx = ebx;
	status->guest_registers.rcx = ecx;
	status->guest_registers.rdx = edx;
	status->vmcb.state_area.rip += 2;
	return 0;
}

/* called when the guest would execute a read or write to a protected MSR */
static u64 handle_msr(struct ProcessorStatus* status) {
	/* the msr the guest is trying to access */
	u32 msr = status->guest_registers.rcx;

	bool write_access = (status->vmcb.control_area.exitinfo1 != 0);
	/* to emulate cpuid_fault, writes and reads to the corresponding MSR are
	 * intercepted */
	if (write_access) {
		u64 value = (status->guest_registers.rdx << 32) |
		            (u32)status->guest_registers.rax;
#ifdef MSR_K7_HWCR_CPUID_USER_DIS_BIT
		/* If the MSR to enable / disable cpuid_fault is being written to */
		if(msr == MSR_K7_HWCR) {
			/* update whether the hypervisor should inject a fault on CPUID */
			status->cpuid_fault = value & BIT_ULL(MSR_K7_HWCR_CPUID_USER_DIS_BIT);
			/* write the value to the register, with the cpuid_fault bit clear */
			do_wrmsr(msr, value & ~BIT_ULL(MSR_K7_HWCR_CPUID_USER_DIS_BIT));
		}
#else
		/* Older kernels will attempt to enable cpuid_fault using the intel
		 * MSR */
		if(msr == MSR_MISC_FEATURES_ENABLES) {
			status->cpuid_fault = value & MSR_MISC_FEATURES_ENABLES_CPUID_FAULT;
		}
#endif
		else {
			/* If we don't care about the MSR, do the write directly */
			do_wrmsr(msr, value);
		}
	} else {
		u64 value;
#ifdef MSR_K7_HWCR_CPUID_USER_DIS_BIT
		/* If the MSR to enable / disable cpuid_fault is being read */
		if(msr == MSR_K7_HWCR) {
			value = do_rdmsr(msr);
			/* reflect the current cpuid_fault status to the guest */
			if(status->cpuid_fault)
				value |= BIT_ULL(MSR_K7_HWCR_CPUID_USER_DIS_BIT);
		}
#else
		/* Older kernels will attempt to enable cpuid_faulting using the intel
		 * MSR */
		if(msr == MSR_MISC_FEATURES_ENABLES) {
			value = 0;
			if(status->cpuid_fault)
				value |= MSR_MISC_FEATURES_ENABLES_CPUID_FAULT;
		}
#endif
		else {
			/* If we don't care about the MSR, do the read directly */
			value = do_rdmsr(msr);
		}
		status->guest_registers.rax = (u32)value;
		status->guest_registers.rdx = (u32)(value >> 32);
	}
	status->vmcb.state_area.rip += 2;
	return 0;
}

/* consistent functions to write segment selectors */
#define define_sel_ops(sel) \
inline static u64 read_ ## sel ## _sel(void) {\
	u16 sel; \
	asm volatile ("movw %%" #sel ", %0" : "=r" (sel) : :); \
	return sel; \
} \
inline static void write_ ## sel ## _sel(u16 sel) {\
	asm volatile ("movw %0, %%" #sel : :"r" (sel) :); \
}
define_sel_ops(ds);
define_sel_ops(es);
define_sel_ops(ss);
inline static u64 read_cs_sel(void) {
	u16 cs;
	asm volatile("movw %%cs, %0" : "=r"(cs) : :);
	return cs;
}
/* a direct move into cs is not a valid instruction, so the value is written
 * via a far jump */
inline static void write_cs_sel(u16 cs) {
	asm volatile("movzwq %0,%%rax\n\t"
	             "pushq %%rax\n\t"
	             "leaq curr_ip(%%rip),%%rax\n\t"
	             "pushq %%rax\n\t"
	             "lretq\n\t"
	             "curr_ip:": : "r"(cs) : "rax");
};

/* To end the virtualization the host needs to put itself the guest was just
 * in, this effectively does the opposite to setup_guest_state */
static void restore_host_state(struct ProcessorStatus* status) {
	struct VMCB* guest_vmcb = &status->vmcb;
	struct desc_ptr gdt_ptr;
	struct desc_ptr idt_ptr;
	/* Load other state that might have changed */
	vmload(status->vmcb_pa);
	
	/* Restore the hsave address before the processor was virtualized */
	do_wrmsr(SVM_MSR_VM_HSAVE_PA, status->prev_hsave_pa);

	do_wrmsr(MSR_EFER, guest_vmcb->state_area.efer);

	idt_ptr.address = guest_vmcb->state_area.idtr.base;
	idt_ptr.size = guest_vmcb->state_area.idtr.limit;
	gdt_ptr.address = guest_vmcb->state_area.gdtr.base;
	gdt_ptr.size = guest_vmcb->state_area.gdtr.limit;

	/* Restore gdt and idt. Done for correctness */
	native_load_gdt(&gdt_ptr);
	native_load_idt(&idt_ptr);

	/* Load segment selectors from the guest. Also for correctness */
	write_es_sel(guest_vmcb->state_area.es.selector);
	write_ss_sel(guest_vmcb->state_area.ss.selector);
	write_ds_sel(guest_vmcb->state_area.ds.selector);
	write_cs_sel(guest_vmcb->state_area.cs.selector);

	/* run_vm will resume running the OS by setting this rip and rsp */
	status->guest_registers.rax = guest_vmcb->state_area.rip;
	status->guest_registers.rsp = guest_vmcb->state_area.rsp;
	
	/* will be used by the OS to cleanup the per processor data */
	status->guest_registers.rbx = (u64)status;
}

/* Everytime an intercepted instruction is excecuted (currently only
 * wrmsr/rdmsr to the cpuid_fault register, cpuid and runvm (required by
 * the processor)), the guest's state is saved and the hypervisor calls
 * this function */
u64 handle_vm_exit(struct ProcessorStatus* status) {
	status->guest_registers.rsp = status->vmcb.state_area.rsp;
	status->guest_registers.rax = status->vmcb.state_area.rax;

	u64 exitcode = status->vmcb.control_area.exitcode;
	u64 result = 0;
	switch(exitcode) {
		case VMEXIT_CPUID:
			result = handle_cpuid(status);
			break;
		case VMEXIT_MSRPROT:
			result = handle_msr(status);
			break;
	}
	if(result) { /* begin the devirtualization process */
		restore_host_state(status);
	}
	status->vmcb.state_area.rsp = status->guest_registers.rsp;
	status->vmcb.state_area.rax = status->guest_registers.rax;
	return result; /* tell run_vm if it should keep running the guest */
}

/* Used to initialize the segment registers (cs, ds, es, ss) in the VMCB */
static void set_descriptor_from_gdt(struct desc_ptr* gdtr, u16 selector,
                                    struct SegmentDescriptor* desc) {
	desc->selector = selector;

	u64 idx = selector & ~0b111; /* Mask out the TI and RPL bits */

	if(!idx) {
		desc->attrib = 0;
		desc->limit = 0;
		desc->base = 0;
		return;
	}

	/* Read the 8 bytes of the descriptor from the gdt, there's also 16-byte
	 * descriptors (e.g. TSS, LDT), but the function is not used for them, so
	 * they're not handled */
	u64 raw = *(u64*) (gdtr->address + idx);

	/* Concatenate the attribute bits */
	desc->attrib = ((raw & (0xFFL << 40)) >> 40) |
	               ((raw & (0xFL << 52)) >> 44);
	/* Concatenate the limit bits */
	desc->limit = (raw & 0xFFFF) | ((raw & (0xFL << 48)) >> 32);
	/* If the granularity is 4kb, store the effective limit */
	if(raw & (0x1L << 55)) desc->limit = (desc->limit << 12) | 0xFFFL;
	/* Concatenate the base address bits */
	desc->base = ((raw & (0xFFFFL << 16)) >> 16) |
	             ((raw & (0xFFL << 32)) >> 16) |
	             ((raw & (0xFFL << 56)) >> 32);
}

/* This setups all of the state needed to run a vm with the current status
 * of the processor */
static void setup_guest_state(struct page* host_status_page,
	                           struct InitialContext* initial_context) {
	u64 host_status_pa = page_to_phys(host_status_page);
	u64 guest_vmcb_pa = host_status_pa + HOST_VMCB_OFFSET;
	u64 host_vmcb_pa = host_status_pa + HOST_HOST_VMCB_OFFSET;
	u64 host_save_pa = host_status_pa + HOST_HOST_SAVE_OFFSET;

	struct ProcessorStatus* host_status = page_address(host_status_page);
	host_status->vmcb_pa = guest_vmcb_pa;
	host_status->host_vmcb_pa = host_vmcb_pa;

	/* used to cleanup after the processor is devirtualized */
	host_status->page_ptr = host_status_page;

	host_status->guest_registers = initial_context->regs;
	struct VMCB* guest_vmcb = &host_status->vmcb;

	struct desc_ptr gdt_ptr;
	struct desc_ptr idt_ptr;

	native_store_gdt(&gdt_ptr);
	store_idt(&idt_ptr);

	/* intercept MSRs defined by MSR prot */
	guest_vmcb->control_area.intercept_vector3.msr_prot = 1;
	guest_vmcb->control_area.msrpm_base_pa = shared_data.msrpm_pa;

	/* intercept the CPUID instruction */
	guest_vmcb->control_area.intercept_vector3.cpuid_inst = 1;

	/* intercept the VMRUN instruction (required to run VMRUN) */
	guest_vmcb->control_area.intercept_vector4.vmrun_inst = 1;

	/* the guest uses it's own address space, 1 is the safest value to use */
	guest_vmcb->control_area.guest_asid = 1;

	u32 eax, ebx, ecx, edx;
	do_cpuid_leaf(0x80000008, &eax, &ebx, &ecx, &edx);
	if(ebx & (1 << 3)) {
		do_cpuid_leaf(0x8000000a, &eax, &ebx, &ecx, &edx);
		if(edx & (1 << 24)) {
			guest_vmcb->control_area.virtualization_control0.invlpg_tlbsync_enable = 1;
		}
	}

	guest_vmcb->state_area.gdtr.base = gdt_ptr.address;
	guest_vmcb->state_area.gdtr.limit = gdt_ptr.size;
	guest_vmcb->state_area.idtr.base = idt_ptr.address;
	guest_vmcb->state_area.idtr.limit = idt_ptr.size;

	u16 cs_selector = read_cs_sel();
	set_descriptor_from_gdt(&gdt_ptr, cs_selector,
	                        &guest_vmcb->state_area.cs);
	u16 ds_selector = read_ds_sel();
	set_descriptor_from_gdt(&gdt_ptr, ds_selector,
	                        &guest_vmcb->state_area.ds);
	u16 es_selector = read_es_sel();
	set_descriptor_from_gdt(&gdt_ptr, es_selector,
	                        &guest_vmcb->state_area.es);
	u16 ss_selector = read_ss_sel();
	set_descriptor_from_gdt(&gdt_ptr, ss_selector,
	                        &guest_vmcb->state_area.ss);

	guest_vmcb->state_area.efer = do_rdmsr(MSR_EFER);
	guest_vmcb->state_area.cr0 = do_read_cr0();
	guest_vmcb->state_area.cr2 = do_read_cr2();
	guest_vmcb->state_area.cr3 = do_read_cr3();
	guest_vmcb->state_area.cr4 = do_read_cr4();

	guest_vmcb->state_area.rflags = initial_context->rflags;
	guest_vmcb->state_area.rsp = initial_context->regs.rsp;
	guest_vmcb->state_area.rip = initial_context->rip;
	guest_vmcb->state_area.rax = initial_context->regs.rax;

	vmsave(guest_vmcb_pa);

	/* Save the hsave address before the hypervisor is loaded */
	/* (If the kvm_amd kernel module is loaded, this value will already be
	 * setup and changing it and trying to run a kvm vm will crash the OS) */
	host_status->prev_hsave_pa = do_rdmsr(SVM_MSR_VM_HSAVE_PA);
	do_wrmsr(SVM_MSR_VM_HSAVE_PA, host_save_pa);

	/* save another copy of the host state, used to provide a more consistent
	 * host state at vmexit */
	vmsave(host_vmcb_pa);
}

static int virtualize_processor(void* processor_number) {
	struct page* host_status_page;
	int order = get_order(sizeof(struct ProcessorStatus));
	host_status_page = alloc_pages(GFP_KERNEL, order);
	if (!host_status_page)
		goto host_status_page_failed;

	unsigned long flags;
	get_cpu();
	local_irq_save(flags);

	memset(page_address(host_status_page), 0, PAGE_SIZE * (1 << order));

	struct InitialContext context;


	/* Capture the context to be used to initialize the guest, since it
	 * returns 1 but the stored state has 0 as it's return, when the guest
	 * starts execution at the stored state it will not enter into the if.
	 * */
	if(capture_context(&context)) {

		do_wrmsr(MSR_EFER, do_rdmsr(MSR_EFER) | EFER_SVME); /* Enable SVME */

		setup_guest_state(host_status_page, &context);
		struct ProcessorStatus* host_status = page_address(host_status_page);

		/* Kinda ugly, effectively sets a CR3 for the host that will
		* always be safe to access the hypervisor's code from
		* */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 9, 0)
        leave_mm();
#else
        leave_mm(smp_processor_id());
#endif
		run_vm(host_status);
		BUG();
	}

	/* Only the guest should run this code */
	put_cpu();

	pr_info("Processor %d virtualized\n", (u32)(u64)processor_number);
	return 0;
host_status_page_failed:
	local_irq_restore(flags);
	put_cpu();

	return -ENOMEM;
}

static int check_svm_on_cpu(void*) {
	return do_rdmsr(MSR_EFER) & EFER_SVME;
}

static bool check_svm_status(void) {
	u32 svm_enabled = 0;
	cpus_read_lock();
	u32 cpu;
	for_each_online_cpu(cpu) {
		svm_enabled |= smp_call_on_cpu(cpu, check_svm_on_cpu, NULL, true);
	}
	cpus_read_unlock();
	return svm_enabled;
}


static int devirtualize_processor(void* processor_number) {
	int order = get_order(sizeof(struct ProcessorStatus));
	unsigned long flags;
	get_cpu();
	local_irq_save(flags);

	u64 rax = UNLOAD_HV_MAGIC;
	u64 rbx, rcx, rdx;
	asm volatile("cpuid":"+a"(rax),"=b"(rbx),"=c"(rcx),"=d"(rdx)::"memory");
	struct ProcessorStatus* status = NULL;

	if(rax != UNLOAD_HV_MAGIC) {
		status = (struct ProcessorStatus*)rbx;
		struct VMCB* guest_vmcb = &status->vmcb;

		do_write_cr3(guest_vmcb->state_area.cr3);
		do_write_cr4(guest_vmcb->state_area.cr4);
		do_write_cr2(guest_vmcb->state_area.cr2);
		do_write_cr0(guest_vmcb->state_area.cr0);
	}

	if(!shared_data.prev_svm_enabled)
		do_wrmsr(MSR_EFER,  do_rdmsr(MSR_EFER) & ~EFER_SVME);

	local_irq_restore(flags);
	put_cpu();
	if(status)__free_pages(status->page_ptr, order);


	pr_info("Processor %d devirtualized\n", (u32)(u64)processor_number);
	return 0;
}

/* called when a Power Management (e.g. suspend) event is about to happen */
static int handle_pm_notification(struct notifier_block* nb, unsigned long action, void *data) {

	if(action == PM_HIBERNATION_PREPARE || action == PM_SUSPEND_PREPARE) {
		/* on suspend or hibernation svm is disabled, so
		 * all processors need to be devirtualized */
		cpus_read_lock();
		u32 cpu;
		for_each_online_cpu(cpu) {
			smp_call_on_cpu(cpu, devirtualize_processor, (void*)(u64)cpu, true);
		}
		cpus_read_unlock();
		/* return the cpuid_fault bit capability to it's previous value */
		if(!shared_data.prev_cpuid_fault_cap)
			clear_bit(X86_FEATURE_CPUID_FAULT,
			          (unsigned long *)(boot_cpu_data.x86_capability));
	}
	if(action == PM_POST_HIBERNATION || action == PM_POST_SUSPEND) {
		/* revirtualize all processors after suspend or hibernation */
		cpus_read_lock();
		u32 cpu;
		for_each_online_cpu(cpu) {
			smp_call_on_cpu(cpu, virtualize_processor, (void*)(u64)cpu, true);
		}
		cpus_read_unlock();
		shared_data.prev_cpuid_fault_cap = test_bit(X86_FEATURE_CPUID_FAULT,
		                      (unsigned long *)(boot_cpu_data.x86_capability));
		set_bit(X86_FEATURE_CPUID_FAULT,
		        (unsigned long *)(boot_cpu_data.x86_capability));
	}
	return 0;
}

static struct notifier_block pm_notifier = {
	.notifier_call = handle_pm_notification
};

static int __init init_emulation(void) {
	if (!check_svm_support()) {
		pr_info("Processor not supported\n");
		return -ENODEV;
	}
	shared_data.prev_svm_enabled = check_svm_status();

	if(shared_data.prev_svm_enabled && !ignore_svm_enabled) {
		pr_info("SVM already enabled\n");
		return -ENODEV;
	}

	shared_data.msrpm_page = alloc_pages(GFP_KERNEL, 1);
	if (!shared_data.msrpm_page)
		goto msrpm_failed;
	shared_data.msrpm_pa = page_to_phys(shared_data.msrpm_page);

	memset(page_address(shared_data.msrpm_page), 0, 0x2000);
	unsigned char* section_1_start = (unsigned char*)
	  page_address(shared_data.msrpm_page);
	unsigned char* section_3_start = (unsigned char*)
	  page_address(shared_data.msrpm_page) + 0x1000;

#ifdef MSR_K7_HWCR_CPUID_USER_DIS_BIT
	set_bit((MSR_K7_HWCR - MSR_PM_BASE3) * 2,
	        (unsigned long*) section_3_start);
	set_bit((MSR_K7_HWCR - MSR_PM_BASE3) * 2 + 1,
	        (unsigned long*) section_3_start);
#else /* on older kernels intercept the intel register instead */
	set_bit((MSR_MISC_FEATURES_ENABLES - MSR_PM_BASE1) * 2,
	        (unsigned long*) section_1_start);
	set_bit((MSR_MISC_FEATURES_ENABLES - MSR_PM_BASE1) * 2 + 1,
	        (unsigned long*) section_1_start);
#endif

	cpus_read_lock();
	u32 cpu;
	for_each_online_cpu(cpu) {
		smp_call_on_cpu(cpu, virtualize_processor, (void*)(u64)cpu, true);
	}
	cpus_read_unlock();
	shared_data.prev_cpuid_fault_cap = test_bit(X86_FEATURE_CPUID_FAULT,
	  (unsigned long *)(boot_cpu_data.x86_capability));
	set_bit(X86_FEATURE_CPUID_FAULT,
	        (unsigned long *)(boot_cpu_data.x86_capability));

	register_pm_notifier(&pm_notifier);

	return 0;

msrpm_failed:
	return -ENOMEM;
}

static void __exit deinit_emulation(void) {
	unregister_pm_notifier(&pm_notifier);
	if(!shared_data.prev_cpuid_fault_cap)
		clear_bit(X86_FEATURE_CPUID_FAULT,
		          (unsigned long *)(boot_cpu_data.x86_capability));
	cpus_read_lock();
	u32 cpu;
	for_each_online_cpu(cpu) {
		smp_call_on_cpu(cpu, devirtualize_processor, (void*)(u64)cpu, true);
	}

	cpus_read_unlock();
	if (shared_data.msrpm_page)
		__free_pages(shared_data.msrpm_page, 1);
}



module_init(init_emulation);
module_exit(deinit_emulation);

MODULE_LICENSE("GPL");
