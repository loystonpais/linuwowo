#ifndef HOST_STATE_H
#define HOST_STATE_H


#define GUEST_RAX_OFFSET 0x00
#define GUEST_RBX_OFFSET 0x08
#define GUEST_RCX_OFFSET 0x10
#define GUEST_RDX_OFFSET 0x18
#define GUEST_RSI_OFFSET 0x20
#define GUEST_RDI_OFFSET 0x28
#define GUEST_RSP_OFFSET 0x30
#define GUEST_RBP_OFFSET 0x38
#define GUEST_R8_OFFSET  0x40
#define GUEST_R9_OFFSET  0x48
#define GUEST_R10_OFFSET 0x50
#define GUEST_R11_OFFSET 0x58
#define GUEST_R12_OFFSET 0x60
#define GUEST_R13_OFFSET 0x68
#define GUEST_R14_OFFSET 0x70
#define GUEST_R15_OFFSET 0x78
#define GUEST_RIP_OFFSET 0x80
#define GUEST_RFLAGS_OFFSET 0x88

#define HOST_STACK_OFFSET 0x000
#define HOST_STACK_SIZE 0x1000
#define HOST_VMCB_OFFSET 0x1000
#define HOST_HOST_VMCB_OFFSET 0x2000
#define HOST_HOST_SAVE_OFFSET 0x3000
#define HOST_VMCB_PA_OFFSET 0x4000
#define HOST_HOST_VMCB_PA_OFFSET 0x4008
#define HOST_REGISTER_OFFSET 0x4010

#ifndef __ASSEMBLER__
#include "vmcb_layout.h"

struct GuestRegisters {
	u64 rax;
	u64 rbx;
	u64 rcx;
	u64 rdx;
	u64 rsi;
	u64 rdi;
	u64 rsp;
	u64 rbp;
	u64 r8;
	u64 r9;
	u64 r10;
	u64 r11;
	u64 r12;
	u64 r13;
	u64 r14;
	u64 r15;
} __attribute__((packed));

static_assert(GUEST_RAX_OFFSET == offsetof(struct GuestRegisters, rax));
static_assert(GUEST_RBX_OFFSET == offsetof(struct GuestRegisters, rbx));
static_assert(GUEST_RCX_OFFSET == offsetof(struct GuestRegisters, rcx));
static_assert(GUEST_RDX_OFFSET == offsetof(struct GuestRegisters, rdx));
static_assert(GUEST_RSI_OFFSET == offsetof(struct GuestRegisters, rsi));
static_assert(GUEST_RDI_OFFSET == offsetof(struct GuestRegisters, rdi));
static_assert(GUEST_RSP_OFFSET == offsetof(struct GuestRegisters, rsp));
static_assert(GUEST_RBP_OFFSET == offsetof(struct GuestRegisters, rbp));
static_assert(GUEST_R8_OFFSET  == offsetof(struct GuestRegisters, r8));
static_assert(GUEST_R9_OFFSET  == offsetof(struct GuestRegisters, r9));
static_assert(GUEST_R10_OFFSET == offsetof(struct GuestRegisters, r10));
static_assert(GUEST_R11_OFFSET == offsetof(struct GuestRegisters, r11));
static_assert(GUEST_R12_OFFSET == offsetof(struct GuestRegisters, r12));
static_assert(GUEST_R13_OFFSET == offsetof(struct GuestRegisters, r13));
static_assert(GUEST_R14_OFFSET == offsetof(struct GuestRegisters, r14));
static_assert(GUEST_R15_OFFSET == offsetof(struct GuestRegisters, r15));

struct InitialContext {
	struct GuestRegisters regs;
	u64 rip;
	u64 rflags;
} __attribute__((packed));
static_assert(GUEST_RIP_OFFSET == offsetof(struct InitialContext, rip));
static_assert(GUEST_RFLAGS_OFFSET == offsetof(struct InitialContext, rflags));

struct ProcessorStatus {
	u8 host_stack[HOST_STACK_SIZE];
	struct VMCB vmcb;
	struct VMCB host_vmcb;
	u8 host_save[0x1000];
	u64 vmcb_pa;
	u64 host_vmcb_pa;
	struct GuestRegisters guest_registers;
	void* page_ptr;
	u64 prev_hsave_pa;
	bool cpuid_fault;
} __attribute__((packed));
static_assert(offsetof(struct ProcessorStatus, host_stack) == HOST_STACK_OFFSET);
static_assert(offsetof(struct ProcessorStatus, vmcb) == HOST_VMCB_OFFSET);
static_assert(offsetof(struct ProcessorStatus, host_vmcb) == HOST_HOST_VMCB_OFFSET);
static_assert(offsetof(struct ProcessorStatus, host_save) == HOST_HOST_SAVE_OFFSET);
static_assert(offsetof(struct ProcessorStatus, vmcb_pa) == HOST_VMCB_PA_OFFSET);
static_assert(offsetof(struct ProcessorStatus, host_vmcb_pa) == HOST_HOST_VMCB_PA_OFFSET);
static_assert(offsetof(struct ProcessorStatus, guest_registers) == HOST_REGISTER_OFFSET);
#endif
#endif

