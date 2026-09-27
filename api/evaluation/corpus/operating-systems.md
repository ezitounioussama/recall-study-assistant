# Operating Systems — Processes, Threads and Scheduling

## Processes
A process is a program in execution. It includes the program counter and registers, the stack, the heap, open file descriptors, and the address space the kernel has mapped for it. The kernel tracks every process in a process control block (PCB), which holds the process identifier (PID), the saved CPU state, the scheduling priority and accounting information.

## Threads
A thread is a unit of execution inside a process. All threads of a process share the address space, the heap and the open files, but each has its own program counter, registers and stack. Creating a thread is roughly an order of magnitude cheaper than creating a process on Linux.

## Scheduling
Round robin gives each ready thread a fixed time slice, or quantum, and preempts it when the quantum expires. A quantum much longer than a typical CPU burst degrades into first-come first-served. Linux's Completely Fair Scheduler keeps ready threads in a red-black tree ordered by virtual runtime.
