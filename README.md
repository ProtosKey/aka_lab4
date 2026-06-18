# Лабораторная работа №4 — Симулятор процессора

**Вариант:** `lisp | risc | harv | mc | tick | binary | stream | port | cstr | prob2`

---

## Содержание

1. [Язык программирования](#1-язык-программирования)
2. [Организация памяти](#2-организация-памяти)
3. [Система команд (ISA)](#3-система-команд-isa)
4. [Транслятор](#4-транслятор)
5. [Модель процессора](#5-модель-процессора)
6. [Тестирование](#6-тестирование)

---

## 1. Язык программирования

Минимальный диалект Lisp: S-выражения, строгий порядок вычисления, всё есть выражение.

### 1.1 Синтаксис (BNF)

```
<program>   ::= { <toplevel> }
<toplevel>  ::= <defun> | <expr>

<defun>     ::= "(" "defun" <ident> "(" { <ident> } ")" <body> ")"
<body>      ::= <expr> { <expr> }          ; значение — последний <expr>

<expr>      ::= <integer>
              | <string>
              | <ident>
              | "(" <setq>  ")"
              | "(" <if>    ")"
              | "(" <loop>  ")"
              | "(" <progn> ")"
              | "(" <call>  ")"

<setq>      ::= "setq" <ident> <expr>
<if>        ::= "if" <expr> <expr> <expr>   ; cond then else — else обязателен
<loop>      ::= "loop" <expr> { <expr> }    ; while cond != 0
<progn>     ::= "progn" <expr> { <expr> }
<call>      ::= <ident> { <expr> }

<integer>   ::= [ "-" ] <digit> { <digit> }
<string>    ::= '"' { <char> } '"'          ; \n \0 \" \\ поддерживаются
<ident>     ::= <istart> { <ichar> }
<istart>    ::= <letter> | "+" | "-" | "*" | "<" | ">" | "=" | "_" | "!" | "?"
<ichar>     ::= <istart> | <digit>
```

Комментарии — `;` до конца строки.

### 1.2 Семантика

| Форма | Результат |
|---|---|
| `IntLit n` | `n` |
| `StrLit s` | адрес первого байта строки в data memory |
| `VarRef x` | значение переменной (параметр или глобал) |
| `Setq x e` | вычислить `e`, записать в `x`, вернуть значение |
| `If c t f` | если `eval(c) != 0` — `eval(t)`, иначе `eval(f)` |
| `Loop c b…` | пока `eval(c) != 0`, вычислять тело; возвращает значение последнего `bk` |
| `Progn e…` | вычислять по порядку, вернуть последнее |
| `DefFun f ps body` | зарегистрировать функцию; значение `0` |
| `Call f a…` | eval args слева направо → вызов → значение последнего выражения тела |

**Вычисление:** аппликативный порядок (call-by-value), слева направо.

**Область видимости:** два уровня — глобальный и фрейм функции.
Внутри `defun` `setq` обращается к слоту параметра, если имя совпадает с параметром; иначе к глобальному слоту (создаётся при первом обращении). Следствие: нерекурсивные хелперы (`div10`, `mod10`, `read-int`) безопасны, но рекурсивные функции, использующие `setq` для «локальных» переменных, некорректны.

**Типы:** единственный числовой тип — 32-битное знаковое целое. Строки — адреса. Булевы: 0 — ложь, любое другое — истина. Сравнения возвращают 0 или 1.

**Встроенные функции:**

| Имя | Арность | Описание |
|---|---:|---|
| `+ - *` | 2 | арифметика (wraparound 2³²) |
| `< > = <= >=` | 2 | сравнение → 0 / 1 |
| `getc` | 0 | прочитать байт из порта 0 |
| `putc` | 1 | записать байт в порт 1 |
| `load` | 1 | `M4[addr]` — слово из data memory |
| `store` | 2 | `M4[addr] ← val` |
| `load-byte` | 1 | `M1[addr]` — байт, знакорасширенный |
| `store-byte` | 2 | `M1[addr] ← val & 0xFF` |
| `halt` | 0 | останов симулятора |

---

## 2. Организация памяти

Гарвардская архитектура: команды и данные в раздельных адресных пространствах.

### 2.1 Регистры

```
x0  (zero) — всегда 0 (аппаратная константа)
x1  (ra)   — адрес возврата
x2  (sp)   — указатель стека (растёт вниз)
x3  (gp)   — база секции глобальных переменных
x5–x7      — временные (t0–t2), caller-saved
x8  (fp)   — указатель фрейма, callee-saved
x10–x17    — аргументы / возвращаемое значение (a0–a7)
x28–x31    — временные (t3–t6), caller-saved
```

### 2.2 Память команд (instruction memory)

```
+------------------------+ 0x0000
| boot stub (5 инструкц) |   LUI/ADDI gp, LUI/ADDI sp, JAL main
+------------------------+ 0x0014
| тела функций           |
|   (в порядке defun)    |
+------------------------+
| main                   |   тело программы, оканчивается HALT
+------------------------+
```

ROM, 4 байта на инструкцию, little-endian. Загружается из `.bin` перед запуском.

### 2.3 Память данных (data memory, 64 KiB)

```
+------------------------+ 0x0000
| строковые литералы     |   NUL-terminated, 1 байт / символ
| (cstr, byte-packed)    |
+------------------------+ GP_BASE   ← gp указывает сюда
| глобальные переменные  |   4 байта / переменная, порядок первого появления
+------------------------+
|   (свободно)           |
+------------------------+ 0xFFFC ↑ stacks grows down
| стек                   |   растёт вниз; sp = 0x10000 при старте
+------------------------+ 0x10000  (=DATA_MEM_SIZE)
```

**Строки** (`cstr`): хранятся в начале data memory до `GP_BASE`. Символы — по 1 байту, терминатор — `\0`. Доступ через `LB` + `SB`.

**Глобалы**: 4-байтные слоты от `GP_BASE`. Доступ: `LW a0, k(gp)` / `SW gp, a0, k`.

**Фрейм функции** (растёт вниз от sp):

```
fp → [ ra       ] 0(fp)
     [ caller fp] 4(fp)
     [ param 0  ] 8(fp)
     [ param 1  ] 12(fp)
     ...
```

Параметры доступны через `LW a0, (8+4*i)(fp)` — `fp` не меняется, пока sp двигается при вложенных вычислениях.

---

## 3. Система команд (ISA)

RISC-архитектура в стиле RV32I. Все инструкции — 32 бита, фиксированная ширина.

### 3.1 Форматы

```
 31      25 24  20 19  15 14 12 11   7 6    0
R  funct7  | rs2  | rs1  |fn3| rd   | opcode
I  imm[11:0]     | rs1  |fn3| rd   | opcode
S  imm[11:5]| rs2 | rs1  |fn3|imm4:0| opcode
B  imm[12|10:5]|rs2| rs1 |fn3|imm4:1|11| opc
U  imm[31:12]               | rd   | opcode
J  imm[20|10:1|11|19:12]    | rd   | opcode
```

Иммедиаты знакорасширяются до 32 бит.

### 3.2 Набор инструкций

| Мнемоника | Формат | Тиков | Операция |
|---|:---:|:---:|---|
| `ADD rd, rs1, rs2` | R | 2 | `rd ← rs1 + rs2` |
| `SUB rd, rs1, rs2` | R | 2 | `rd ← rs1 - rs2` |
| `MUL rd, rs1, rs2` | R | 2 | `rd ← (rs1 * rs2)[31:0]` |
| `SLL/SRL/AND/OR` | R | 2 | битовые / сдвиги |
| `ADDI/ANDI/ORI/SLLI/SRLI` | I | 2 | то же с иммедиатом |
| `LB rd, imm(rs1)` | I | 3 | `rd ← sign_ext(M1[rs1+imm])` |
| `LW rd, imm(rs1)` | I | 3 | `rd ← M4[rs1+imm]` |
| `SB rs2, imm(rs1)` | S | 3 | `M1[rs1+imm] ← rs2[7:0]` |
| `SW rs2, imm(rs1)` | S | 3 | `M4[rs1+imm] ← rs2` |
| `BEQ rs1, rs2, imm` | B | 2 | `if rs1==rs2: PC += imm` |
| `BNE / BLT / BGE` | B | 2 | аналогично |
| `JAL rd, imm` | J | 2 | `rd←PC+4; PC+=imm` |
| `JALR rd, rs1, imm` | I | 2 | `rd←PC+4; PC←(rs1+imm)&~1` |
| `LUI rd, imm` | U | 2 | `rd ← imm[31:12] << 12` |
| `IN rd, port` | I | 2 | `rd ← PORT_IN[port]` |
| `OUT rs1, port` | S | 2 | `PORT_OUT[port] ← rs1[7:0]` |
| `HALT` | I | 2 | останов |

Тик fetch (µPC=0x00) включён в счёт.

`BLT` использует флаг `lt_signed` из ALU:
`(a[31] ≠ b[31]) ? a[31] : (a−b)[31]` — корректен при переполнении.

### 3.3 Ввод-вывод (`port`, `stream`)

Порт-маппированный, потоковый:
- **Порт 0** (in): `IN rd, 0` — извлекает символ из входного FIFO. Если FIFO пуст — HALT с причиной `in-empty`.
- **Порт 1** (out): `OUT rs1, 1` — добавляет байт в выходной буфер.

### 3.4 Бинарное представление (`binary`)

Транслятор создаёт два файла:

```
prog.bin       — сырой бинарник, 4 байта / инструкция, little-endian
prog.data.bin  — начальное содержимое data memory
prog.lst       — дизассемблер (формат: <ADDR> - <HEXCODE> - <mnemonic>)
```

Пример строки листинга:
```
00B0 - F65FF0EF - jal ra, print-str
```

---

## 4. Транслятор

### 4.1 CLI

```bash
python -m src.translator <source.lisp> <output_stem>

# Пример:
python -m src.translator tests/golden/prob2/source.lisp out/prob2
# Создаёт: out/prob2.bin  out/prob2.data.bin  out/prob2.lst
```

### 4.2 Этапы трансляции

```
source.lisp
    │
    ├── Лексер (ast.py)
    │     tokenize() → список токенов: (, ), INT, STR, IDENT
    │
    ├── Парсер (ast.py)
    │     _Parser.parse_program() → список AST-узлов
    │     (IntLit, StrLit, VarRef, Setq, If, Loop, Progn, DefFun, Call)
    │
    ├── Pre-scan (codegen.py)
    │     Обход AST: собрать StrLit → DataSection (строки в data memory)
    │     Собрать DefFun → таблица функций
    │     DataSection.freeze() → зафиксировать GP_BASE
    │
    ├── Генерация кода (codegen.py)
    │     Emit boot stub → defun bodies → main body → HALT
    │     Каждый AST-узел → шаблон из language.md §6.3
    │     Глобальные переменные добавляются в DataSection по мере встречи
    │
    └── Ассемблирование (assembler.py)
          Pass 1: emit слова, fixup-записи для меток
          Pass 2: patch branch/jump immediates
          → bytes + listing
```

### 4.3 Шаблоны генерации кода (ключевые)

**Загрузка константы** (LUI+ADDI carry-correction):
```lisp
; (setq x 0xB2D05E00)  → 3 000 000 000 / -1 294 967 296 (signed)
LUI  a0, 0xB2D06     ; a0 = 0xB2D06000
ADDI a0, a0, -512    ; a0 = 0xB2D05E00
```

**Бинарная операция** `(+ A B)`:
```asm
<code A>            ; a0 = A
addi sp, sp, -4
sw   a0, 0(sp)      ; push A
<code B>            ; a0 = B
lw   t0, 0(sp)      ; t0 = A
addi sp, sp, 4
add  a0, t0, a0     ; a0 = A + B
```

**Ветвление** `(if c t f)`:
```asm
<code c>
beq a0, x0, L_else
<code t>
jal x0,  L_end
L_else: <code f>
L_end:
```

**Цикл** `(loop c b1 … bk)`:
```asm
addi sp, sp, -4
sw   x0, 0(sp)      ; default result = 0
L_head:
<code c>
beq  a0, x0, L_end
<code b1> … <code bk>
sw   a0, 0(sp)      ; save last body value
jal  x0, L_head
L_end:
lw   a0, 0(sp)
addi sp, sp, 4
```

**Пролог/эпилог функции** с `n` параметрами:
```asm
f:  addi sp, sp, -(8+4n)
    sw   ra, 0(sp)
    sw   fp, 4(sp)
    addi fp, sp, 0      ; fp = new frame base
    sw   a0, 8(fp)      ; param 0
    sw   a1, 12(fp)     ; param 1
    <body>              ; result in a0
    addi sp, fp, 0      ; reset sp
    lw   ra, 0(sp)
    lw   fp, 4(sp)
    addi sp, sp, (8+4n)
    jalr x0, ra, 0
```

---

## 5. Модель процессора

### 5.1 Datapath (блок-схема)

```
        inst_mem
           │
  ┌────────┴──────────────────────────────────────────────────────┐
  │  PC ──► IM ──► IR ──► декодер полей (opcode, rd, rs1, rs2,   │
  │                        funct3, funct7, imm)                   │
  │                 │                                             │
  │              ┌──┴───────────────────────┐                    │
  │              │      Register File       │                    │
  │              │  rs1_val   rs2_val   W   │                    │
  │              └──┬───────────┬───────────┘                    │
  │                 │           │                                 │
  │           port_a│   ┌──mux──┘ ← is_imm ← (imm / rs2)        │
  │                 │   │port_b                                   │
  │              ┌──┴───┴──┐                                     │
  │              │   ALU   │ ── alu_out ──┬── mem_addr latch      │
  │              │         │             │                        │
  │              └────┬────┘          data_mem                   │
  │               zero│lt_signed         │mem_out                │
  │                   │               ┌──┴──────┐                │
  │           ┌───────┴───────────────┤  WB mux │◄── io_in       │
  │           │  PC_SRC mux           │ (5-to-1)│◄── PC+4        │
  │           │  (PC+4 / PC+imm /     │         │◄── imm_hi      │
  │           │   alu_out / BR_*)     └────┬────┘                │
  │           │                      data_w│                     │
  │           └──► new PC                  └──► regs[rd]         │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
                         ↑ control signals от CU (microcode)
```

### 5.2 Control Unit (микропрограммный, `mc`)

Состояние CU — регистр `µPC`. Каждый такт:
1. Читает micro-инструкцию из ROM по `µPC`.
2. Выставляет управляющие сигналы.
3. Комбинационно вычисляет результаты (ALU, MEM, IO).
4. На фронте тактового импульса фиксирует новое состояние (PC, IR, regs, data_mem, µPC).

**Формат микрослова (20 бит, упакованных в 32-битное слово):**

```
 бит:  19 18 │ 17 15 │ 14 12 │ 11 10 │  9  7 │  6  4 │  3  │  2  │  1  │  0
        SEQ  │PC_SRC │WB_SEL │ IO_OP │MEM_OP │ALU_OP │IS_IM│RW   │PW   │IW
```

| Поле | Ширина | Описание |
|---|:---:|---|
| `IR_WE` (IW) | 1 | защёлкнуть IR ← instr |
| `PC_WE` (PW) | 1 | защёлкнуть PC ← pc_mux_out |
| `REGS_WE` (RW) | 1 | записать regs[rd] ← data_w |
| `IS_IMM` | 1 | ALU port_b: 0=rs2, 1=imm |
| `ALU_OP` | 3 | NOP/ADD/SUB/MUL/SLL/SRL/AND/OR |
| `MEM_OP` | 3 | NONE/RD_B/RD_W/WR_B/WR_W |
| `IO_OP` | 2 | NONE/IN/OUT |
| `WB_SEL` | 3 | ALU/MEM/PC4/IMM_HI/IO_IN |
| `PC_SRC` | 3 | PC4/PC_IMM/ALU/BR_EQ/BR_NE/BR_LT/BR_GE |
| `SEQ` | 2 | NEXT/FETCH/DECODE/HALT |

**Таблица декодирования (часть):**

| Опкод | funct3 | funct7 | Инструкция | µPC |
|---|---|---|---|---|
| `0110011` | `000` | `0000000` | ADD | `0x01` |
| `0110011` | `000` | `0000001` | MUL | `0x03` |
| `0000011` | `010` | — | LW | `0x0F` |
| `1100011` | `100` | — | BLT | `0x17` |
| `1101111` | — | — | JAL | `0x19` |
| `0001011` | `000` | — | IN | `0x1C` |
| `0101011` | `000` | — | OUT | `0x1D` |
| `1110011` | `000` | — | HALT | `0x1E` |

**Микропрограмма выборки (µPC=0x00):**

```
µFETCH: IR_WE=1, SEQ=DECODE
  → instr ← IM[PC]
  → IR ← instr
  → µPC ← decode_table[opcode, funct3, funct7]
```

**Пример: LW x10, 8(x2)** (3 такта):

| Такт | µPC | Событие |
|---:|---|---|
| 1 | `0x00` | `IR<=00812503 µPC<=0F` |
| 2 | `0x0F` | ALU: rs1+imm=0x108; `data_mem.addr<=00000108 µPC<=10` |
| 3 | `0x10` | `regs[10]<=DEADBEEF PC<=00000084 µPC<=00` |

### 5.3 Формат трейса

Каждый такт — одна строка:
```
tick=<N> PC=<hex32> IR=<hex32> µPC=<hex8> | <events>
```

Примеры событий: `IR<=...`, `PC<=...`, `regs[n]<=...`, `M4[addr]<=...`, `IN port=0, value=41`, `OUT port=1, value=48`, `BRANCH taken=1`, `HALT reason=halt`.

### 5.4 CLI симулятора

```bash
python -m src.simulator <prog.bin> [data.bin] [input]

# input — строка или путь к файлу
python -m src.simulator out/hello.bin out/hello.data.bin ""
python -m src.simulator out/cat.bin   out/cat.data.bin   "Hello!"
```

---

## 6. Тестирование

### 6.1 Запуск тестов

```bash
python -m pytest tests/ -v       # 25 тестов
python -m pytest tests/ -q       # краткий вывод
python -m pytest tests/ -k sort  # один тест
```

### 6.2 Состав golden-тестов

| Тест | Описание | Инстр. | Тиков | Вход | Выход |
|---|---|---:|---:|---|---|
| `hello` | Hello, World! | 46 | 691 | — | `Hello, World!\n` |
| `cat` | Echo input | 16 | 112 | `Hello!\n` | `Hello!\n` |
| `hello_user_name` | Запрос имени и приветствие | 123 | 2 020 | `Alice\n` | `What is your name?\nHello, Alice!\n` |
| `sort` | Bubble sort, 0-terminated | 443 | 6 882 | `3\n1\n4\n1\n5\n0\n` | `1\n1\n3\n4\n5\n` |
| `prob2` | Euler #6 (N=10) | 348 | 37 943 | `10\n` | `2640\n` |
| `double_prec` | 64-bit сложение | 270 | 457 | — | `1 0\n` |

### 6.3 Что проверяют тесты

| Тест-функция | Что проверяется |
|---|---|
| `test_output` | вывод симулятора совпадает с `expected_output.txt` |
| `test_listing_format` | каждая строка `.lst` — `XXXX - XXXXXXXX - mnemonic` |
| `test_binary_properties` | `.bin` ненулевой, кратен 4, нет нулевых опкодов |
| `test_trace_sanity` | тики монотонны, PC выровнен на такте выборки |
| `test_isa_coverage` | все классы ISA-инструкций исполнились хотя бы раз |

### 6.4 Примеры трасс

**hello** (первые 12 и последние 3 такта из 691):
```
tick=1  PC=00000000 IR=00000000 µPC=00 | IR<=01000193 µPC<=08
tick=2  PC=00000000 IR=01000193 µPC=08 | regs[3]<=00000010 PC<=00000004 µPC<=00
tick=3  PC=00000004 IR=01000193 µPC=00 | IR<=00018193 µPC<=08
tick=4  PC=00000004 IR=00018193 µPC=08 | regs[3]<=00000010 PC<=00000008 µPC<=00
tick=5  PC=00000008 IR=00018193 µPC=00 | IR<=00010137 µPC<=1B
tick=6  PC=00000008 IR=00010137 µPC=1B | regs[2]<=00010000 PC<=0000000C µPC<=00
tick=7  PC=0000000C IR=00010137 µPC=00 | IR<=00010113 µPC<=08
tick=8  PC=0000000C IR=00010113 µPC=08 | regs[2]<=00010000 PC<=00000010 µPC<=00
tick=9  PC=00000010 IR=00010113 µPC=00 | IR<=08C0006F µPC<=19
tick=10 PC=00000010 IR=08C0006F µPC=19 | PC<=0000009C µPC<=00
tick=11 PC=0000009C IR=08C0006F µPC=00 | IR<=00000513 µPC<=08
tick=12 PC=0000009C IR=00000513 µPC=08 | regs[10]<=00000000 PC<=000000A0 µPC<=00
...
tick=689 PC=00000098 IR=00008067 µPC=1A | PC<=000000B4 µPC<=00
tick=690 PC=000000B4 IR=00008067 µPC=00 | IR<=00000073 µPC<=1E
tick=691 PC=000000B4 IR=00000073 µPC=1E | HALT reason=halt
```

Такты 1–10 — boot stub (загрузка gp, sp, прыжок в main). Такт 10 — `JAL x0, main`.

**double\_prec** — 64-bit сложение `(0, −1) + (0, 1) = (1, 0)`:
```
; r-lo = (-1) + 1 = 0  (оборачивается в 32 битах)
; carry: al_neg=1, bl_neg=0, rl_neg=0 → c1=0, c2=1 → carry=1
; r-hi = 0 + 0 + 1 = 1
; вывод: "1 0"
```

### 6.5 Листинг hello (полный)

```
0000 - 01000193 - addi gp, x0, 16       ; boot: gp = GP_BASE
0004 - 00018193 - addi gp, gp, 0
0008 - 00010137 - lui sp, 0x00010        ; boot: sp = 0x10000
000C - 00010113 - addi sp, sp, 0
0010 - 08C0006F - jal x0, main          ; boot → main
0014 - FF410113 - addi sp, sp, -12      ; print-str prologue
0018 - 00112023 - sw ra, 0(sp)
001C - 00812223 - sw fp, 4(sp)
0020 - 00010413 - addi fp, sp, 0
0024 - 00A42423 - sw a0, 8(fp)          ; store param p
0028 - 00842503 - lw a0, 8(fp)          ; c = load-byte(p)
002C - 00050503 - lb a0, 0(a0)
0030 - 00A1A023 - sw a0, 0(gp)          ; global c = first char
0034 - FFC10113 - addi sp, sp, -4       ; loop: push default 0
0038 - 00012023 - sw x0, 0(sp)
003C - 0001A503 - lw a0, 0(gp)          ; L_head: load c
0040 - 04050063 - beq a0, x0, .Lend2   ; while c != 0
0044 - 0001A503 - lw a0, 0(gp)          ; putc(c)
0048 - 000500AB - out a0, 1
004C - 00842503 - lw a0, 8(fp)          ; p + 1
0050 - FFC10113 - addi sp, sp, -4
0054 - 00A12023 - sw a0, 0(sp)
0058 - 00100513 - addi a0, x0, 1
005C - 00012283 - lw t0, 0(sp)
0060 - 00410113 - addi sp, sp, 4
0064 - 00A28533 - add a0, t0, a0
0068 - 00A42423 - sw a0, 8(fp)          ; p = p + 1
006C - 00842503 - lw a0, 8(fp)          ; c = load-byte(p)
0070 - 00050503 - lb a0, 0(a0)
0074 - 00A1A023 - sw a0, 0(gp)          ; global c = new char
0078 - 00A12023 - sw a0, 0(sp)          ; save loop result
007C - FC1FF06F - jal x0, .Lhead1
0080 - 00012503 - lw a0, 0(sp)          ; loop result
0084 - 00410113 - addi sp, sp, 4
0088 - 00040113 - addi sp, fp, 0        ; print-str epilogue
008C - 00012083 - lw ra, 0(sp)
0090 - 00412403 - lw fp, 4(sp)
0094 - 00C10113 - addi sp, sp, 12
0098 - 00008067 - jalr x0, ra, 0
009C - 00000513 - addi a0, x0, 0        ; main: arg = addr of "Hello, World!\n"
00A0 - FFC10113 - addi sp, sp, -4
00A4 - 00A12023 - sw a0, 0(sp)
00A8 - 00012503 - lw a0, 0(sp)
00AC - 00410113 - addi sp, sp, 4
00B0 - F65FF0EF - jal ra, print-str
00B4 - 00000073 - halt
```

---

## Структура проекта

```
src/
├── micro/
│   ├── enums.py          # AluOp, MemOp, IoOp, WbSel, PcSrc, Seq
│   ├── microcode_rom.py  # ROM (31 µ-инструкция) + decode table
│   ├── data_path.py      # Все регистры, памяти, I/O, ALU
│   ├── control_unit.py   # µPC, step() → TickTrace
│   └── command.py        # Энкодеры R/I/S/B/U/J (используются в тестах)
├── translator/
│   ├── ast.py            # Лексер + парсер → AST
│   ├── assembler.py      # Двухпроходный ассемблер + листинг
│   ├── codegen.py        # Lowering AST → инструкции
│   └── __main__.py       # CLI: python -m src.translator
└── simulator.py          # CLI: python -m src.simulator + run()

tests/
├── test_golden.py
└── golden/
    ├── hello/            source.lisp  input.txt  expected_output.txt
    ├── cat/
    ├── hello_user_name/
    ├── sort/
    ├── prob2/
    └── double_prec/
```
