obj-m += cpuid_fault_emulation.o
cpuid_fault_emulation-y := src/cpuid_fault_emulation.o src/capture_context.o src/run_vm.o

PWD := $(CURDIR)
ccflags-y += -I$(src)/inc
asflags-y += -I$(src)/inc


NOCLANG := CONFIG_CLANG_VERSION=0

KERNEL := $(if $(KERNEL),$(KERNEL),$(shell uname -r))

ifneq ($(shell grep "CONFIG_CLANG_VERSION" /lib/modules/$(KERNEL)/build/.config), $(NOCLANG))
	LLVM := LLVM=1
endif


all:
	echo $(MAKE) $(LLVM) -C /lib/modules/$(KERNEL)/build M=$(PWD) modules
	$(MAKE) $(LLVM) -C /lib/modules/$(KERNEL)/build M=$(PWD) modules

clean:
	$(MAKE) -C /lib/modules/$(KERNEL)/build M=$(PWD) clean
