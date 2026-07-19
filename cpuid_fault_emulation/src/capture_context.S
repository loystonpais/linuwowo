#include <linux/linkage.h>
#include <asm/asm.h>
#include <host_state.h>

#define save_to_offset(val, REG)  movq val , GUEST_ ## REG ## _OFFSET (% _ASM_ARG1 )
SYM_FUNC_START(capture_context)
#ifdef ENDBR
        ENDBR
#endif
        save_to_offset($0, RAX) /* save 0 for guest rax */
        save_to_offset(%rbx, RBX)
        save_to_offset(%rcx, RCX)
        save_to_offset(%rdx, RDX)
        save_to_offset(%rsi, RSI)
        save_to_offset(%rdi, RDI)
        save_to_offset(%rbp, RBP)

        leaq 8(%rsp),%rax /* rsp after ret */
        save_to_offset(%rax, RSP)

        save_to_offset(%r8, R8)
        save_to_offset(%r9, R9)
        save_to_offset(%r10, R10)
        save_to_offset(%r11, R11)
        save_to_offset(%r12, R12)
        save_to_offset(%r13, R13)
        save_to_offset(%r14, R14)
        save_to_offset(%r15, R15)

        movq (%rsp), %rax /* return addr*/
        save_to_offset(%rax, RIP)

        pushfq
        popq %rax /* rflags */
        save_to_offset(%rax, RFLAGS)

        mov $1, %rax;
        RET

SYM_FUNC_END(capture_context)
