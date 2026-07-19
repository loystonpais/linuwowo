#include <linux/linkage.h>
#include <asm/asm.h>
#include <host_state.h>

#define save_to_offset_from(val, off, from)  movq val, off -(HOST_STACK_OFFSET + HOST_STACK_SIZE) (from)
#define mov_from_offset_from(off, reg, from)  movq off -(HOST_STACK_OFFSET + HOST_STACK_SIZE) (from), reg
#define save_to_offset(val, off) save_to_offset_from(val, off, %rsp)
#define mov_from_offset(off, reg) mov_from_offset_from(off, reg, %rsp)
#define save_to_reg_from(val, REG, from)  save_to_offset_from(val, HOST_REGISTER_OFFSET + GUEST_ ## REG ## _OFFSET, from)
#define mov_from_reg_from(REG, reg, from) mov_from_offset_from(HOST_REGISTER_OFFSET + GUEST_ ## REG ## _OFFSET, reg, from)
#define save_to_reg(val, REG)  save_to_reg_from(val, REG, %rsp)
#define mov_from_reg(REG, reg) mov_from_reg_from(REG, reg, %rsp)
SYM_CODE_START(run_vm)
#ifdef ENDBR
        ENDBR
#endif
        leaq HOST_STACK_OFFSET + HOST_STACK_SIZE(%_ASM_ARG1), %rsp

vmloop:
        mov_from_offset(HOST_HOST_VMCB_PA_OFFSET, %rax)
        vmsave

        mov_from_offset(HOST_VMCB_PA_OFFSET, %rax)
        vmload

        mov_from_reg(RBX, %rbx)
        mov_from_reg(RCX, %rcx)
        mov_from_reg(RDX, %rdx)
        mov_from_reg(RSI, %rsi)
        mov_from_reg(RDI, %rdi)
        mov_from_reg(RBP, %rbp)

        mov_from_reg(R8, %r8)
        mov_from_reg(R9, %r9)
        mov_from_reg(R10, %r10)
        mov_from_reg(R11, %r11)
        mov_from_reg(R12, %r12)
        mov_from_reg(R13, %r13)
        mov_from_reg(R14, %r14)
        mov_from_reg(R15, %r15)

        vmrun

        vmsave

        mov_from_offset(HOST_HOST_VMCB_PA_OFFSET, %rax)
        vmload

        save_to_reg(%rbx, RBX)
        save_to_reg(%rcx, RCX)
        save_to_reg(%rdx, RDX)
        save_to_reg(%rsi, RSI)
        save_to_reg(%rdi, RDI)
        save_to_reg(%rbp, RBP)

        save_to_reg(%r8, R8)
        save_to_reg(%r9, R9)
        save_to_reg(%r10, R10)
        save_to_reg(%r11, R11)
        save_to_reg(%r12, R12)
        save_to_reg(%r13, R13)
        save_to_reg(%r14, R14)
        save_to_reg(%r15, R15)

        leaq -HOST_STACK_SIZE(%rsp), %_ASM_ARG1

        /* Save volatile XMM registers */
        sub $0x80, %rsp
        movaps %xmm0, 0x20(%rsp)
        movaps %xmm1, 0x30(%rsp)
        movaps %xmm2, 0x40(%rsp)
        movaps %xmm3, 0x50(%rsp)
        movaps %xmm4, 0x60(%rsp)
        movaps %xmm5, 0x70(%rsp)

        sub $0x8, %rsp
        call handle_vm_exit
        add $0x8, %rsp

        /* Restore volatile XMM registers */
        movaps 0x70(%rsp), %xmm5
        movaps 0x60(%rsp), %xmm4
        movaps 0x50(%rsp), %xmm3
        movaps 0x40(%rsp), %xmm2
        movaps 0x30(%rsp), %xmm1
        movaps 0x20(%rsp), %xmm0
        add $0x80, %rsp

        test %rax, %rax

        jz vmloop

        mov_from_reg(RBX, %rbx) /* now holds rflags */
        pushq %rbx
        popfq
        leaq (%rsp), %rax;
        mov_from_reg(RBX, %rbx)
        mov_from_reg(RCX, %rcx)
        mov_from_reg(RDX, %rdx)
        mov_from_reg(RSI, %rsi)
        mov_from_reg(RDI, %rdi)
        mov_from_reg(RBP, %rbp)

        mov_from_reg(R8, %r8)
        mov_from_reg(R9, %r9)
        mov_from_reg(R10, %r10)
        mov_from_reg(R11, %r11)
        mov_from_reg(R12, %r12)
        mov_from_reg(R13, %r13)
        mov_from_reg(R14, %r14)
        mov_from_reg(R15, %r15)

        mov_from_reg(RSP, %rsp)
        mov_from_reg_from(RAX, %rax, %rax) /* now holds rip */

        stgi
        pushq %rax
        RET


SYM_CODE_END(run_vm)
