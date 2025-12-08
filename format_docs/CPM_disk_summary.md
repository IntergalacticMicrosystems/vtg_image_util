# CP/M-86 Floppy Disk Image Summary

All 11 disk images boot successfully on the Victor 9000 / Sirius I.

## Disk Overview

| Disk | CP/M Version | E/A System | Keyboard | Description |
|------|--------------|------------|----------|-------------|
| 91.img | N/A (Games menu) | N/A | N/A | Games disk |
| 105.img | CP/M-86 1.1 | Release 2.2a | English | Utilities |
| 124.img | CP/M-86 1.0 | Release 2.2 | English | System utilities |
| 432.img | CP/M-86 1.0 | Version 2.2a | Deutsch 01 | German system utilities |
| 433.img | CP/M-86 1.0 | Version 2.2 | Deutsch 01 | German development tools |
| 435.img | CP/M-86 1.1 | Version 2.4 | Deutsch 02a | German WordStar disk |
| 436.img | CP/M-86 1.0 | Version 2.2a | Standard Rep | System utilities |
| 437.img | CP/M-86 1.0 | Version 2.2a | Deutsch 01 | Minimal utilities |
| 438.img | CP/M-86 1.0 | Version 2.2a | Deutsch 01 | Speech/voice disk |
| 584.img | CP/M-86 1.0 | Version 2.2 | Deutsch 01 | German development tools |
| 587.img | CP/M-86 1.0 | Version 2.2 | Deutsch 01 | Development tools |

---

## Detailed File Listings

### 91.img - Games Disk
**System:** Custom games menu (no CP/M prompt)

Files shown on games menu:
- SPACEWAR - "Nur den Namen tippen und die Returntaste"
- Mastermind - "BASIC MASTER tippen"
- Drucker - Printer utility

### 105.img - Utilities
**System:** CP/M-86 1.1, Release 2.2a

```
A: BASIC86  CMD : BDDT     CMD : DDT86   CMD : ED      CMD
A: FORMAT   CMD : GENCMD   CMD : PIP     CMD : STAT    CMD
A: SUBMIT   CMD : XDIR     CMD : ASM86   CMD : EFONT   CMD
A: GRAFIX   CMD : TERM     CMD : MEMORY  CMD : PAUL    SUB
A: SEDIT    CMD : TOD      CMD : HP-IL   CMD
```

### 124.img - System Utilities
**System:** CP/M-86 1.0, Release 2.2

```
A: PIP      CMD : STAT     CMD : SUBMIT  CMD : PBASIC86 CMD
A: FORMAT   CMD : FIXLABEL CMD : BOOTCOPY CMD : ED      CMD
A: DCOPY    CMD : UDCCALC  CMD
```

### 432.img - German System Utilities
**System:** CP/M-86 1.0, Version 2.2a (German)

```
A: BOOTCOPY CMD : DCOPY    CMD : ED      CMD : FIXLABEL CMD
A: FORMAT   CMD : GENCMD   CMD : PIP     CMD : STAT    CMD
A: SUBMIT   CMD : UDCCALC  CMD : VERS2   CMD
```

### 433.img - German Development Tools
**System:** CP/M-86 1.0, Version 2.2 (German)

```
A: ASM86    CMD : GENCMD   CMD : FIXLABEL CMD : PBASIC86 CMD
A: FORMAT   CMD : BASIC86  CMD : DCOPY   CMD : PIP     CMD
A: BOOTCOPY CMD : 132C     CMD : DDT86   CMD : ED      CMD
A: STAT     CMD : SUBMIT   CMD : test        : TEST
A: ALLOC    CMD : CEDIT    BAS : UPLOAD  BAS : CHARGEN SUB
A: GERM01   CHR : CEDIT    USE : UDCCALC CMD
```

### 435.img - German WordStar Disk
**System:** CP/M-86 1.1, Version 2.4 (German)

```
A: WS-I     CMD : RDMSDOS  DOC : RDMSDOS CMD : TOD     CMD
A: CALC     CMD : SUBMIT   CMD : DCOPY   CMD : X       CMD
A: BOOTCOPY CMD : FORMAT   CMD : VOC1    CMD : HELP    HLP
A: 132C     CMD : ED       CMD : HDRIVE  CMD : START   SUB
A: 80       CMD : TIME     CMD : SEX     CMD : HSPOOL  CMD
A: DO       CMD : MOVEIT   CMD : 9600    CMD : TEST    BAK
A: UK-BAUM  BAK : DRUCKER  PAR : DRUCKER BAK : WSI     CMD
A: PINSTALL BAS : SET      CMD : WS      KEY : STUDIO  BAK
A: PBASIC86 CMD : DRUCK    CMD : WS      CMD : VERS2   BAS
A: DEMO         : WSMSGS   OVR : PAULWS  CMD : WSOULY1 OVR
A: BASIC86  CMD : TEST         : UK-BAUM V1  : DEMO    BAK
                                             : STUDIO
```

### 436.img - System Utilities
**System:** CP/M-86 1.0, Version 2.2a (Standard Rep keyboard, HP-41 charset)

```
A: RESET    CMD : STAT     CMD : PIP     CMD : ED      CMD
A: ASM86    CMD : GENCMD   CMD : DDT86   CMD : TERM    CMD
A: 132C     CMD : GRAFIX   CMD : EFONT   CMD : SEDIT   CMD
A: DUMP     CMD : SPACEWAR CMD : BASIC   CMD : HP-IL   CMD
A: ESC      CMD : MASTER   BAS : DRUCKER CMD : MEMORY  CMD
A: FORMAT   CMD : DCOPY    CMD : SAMPLE  CHR : TEST
A: TEST     BAK
```

### 437.img - Minimal Utilities
**System:** CP/M-86 1.0, Version 2.2a (German)

```
A: PIP      CMD : STAT     CMD : SUBMIT  CMD : PBASIC86 CMD
A: FORMAT   CMD : FIXLABEL CMD : BOOTCOPY CMD : ED      CMD
A: DCOPY    CMD : UDCCALC  CMD
```

### 438.img - Speech/Voice Disk
**System:** CP/M-86 1.0, Version 2.2a (German)

```
A: READ     CMD : WAIT     CMD : WSPEAK  CMD : SPEAK   CMD
A: ENABLE   CMD : VOCEDS   CMD : FIRE    CMD : DCOPY   CMD
A: STAT     CMD : SUBMIT   CMD : PIP     CMD : PAUL    SUB
A: +++++++  +++ : +++++++      : +++++++     : +++     : +++++++
A: 25TRE    SND : KARL     SND : PAUL    BAK : VOC     SUB
A: BRAND    SND : ED           : DISCOHO SND : DISCII  SND
A: MES      SND
```

### 584.img - German Development Tools
**System:** CP/M-86 1.0, Version 2.2 (German)

```
A: ASM86    CMD : GENCMD   CMD : FIXLABEL CMD : PBASIC86 CMD
A: FORMAT   CMD : BASIC86  CMD : DCOPY   CMD : PIP     CMD
A: BOOTCOPY CMD : 132C     CMD : DDT86   CMD : ED      CMD
A: STAT     CMD : SUBMIT   CMD : test        : TEST
A: ALLOC    CMD : CEDIT    BAS : UPLOAD  BAS : CHARGEN SUB
A: GERM01   CHR : CEDIT    USE : UDCCALC CMD : PAUL    BAK
A: PAUL         : CEDIT    BAK : CEDIT       : RY
A: RY       BAK : tx       BAS : TX      BAK : TX
A: rxok     BAS : RXOK     BAK : RXOK    BAS : RXOK-BAS BAK
A: RXOK-BAS     : RXTEST1  BAS : RXTEST2 BAS : PORTSET BAS
A: tx10     BAS : TX10         : BAS
```

### 587.img - Development Tools
**System:** CP/M-86 1.0, Version 2.2 (German)

```
A: ASM86    CMD : GENCMD   CMD : FIXLABEL CMD : PBASIC86 CMD
A: FORMAT   CMD : BASIC86  CMD : DCOPY   CMD : PIP     CMD
A: BOOTCOPY CMD : 132C     CMD : DDT86   CMD : ED      CMD
A: STAT     CMD : SUBMIT   CMD : test        : TEST
A: ALLOC    CMD : CEDIT    BAS : UPLOAD  BAS : CHARGEN SUB
A: GERM01   CHR : CEDIT    USE : UDCCALC CMD
```

---

## Common Utilities Across Disks

| Utility | Description | Found On |
|---------|-------------|----------|
| PIP | Peripheral Interchange Program (file copy) | Most disks |
| STAT | Disk/file statistics | Most disks |
| FORMAT | Disk formatter | Most disks |
| ED | Line editor | Most disks |
| SUBMIT | Batch file processor | Most disks |
| ASM86 | 8086 assembler | 105, 433, 436, 584, 587 |
| DDT86 | Dynamic Debugging Tool | 105, 433, 436, 584, 587 |
| GENCMD | Generate CMD file | 105, 432, 433, 584, 587 |
| BASIC86 | BASIC interpreter | 105, 433, 435, 584, 587 |
| PBASIC86 | Personal BASIC-86 | 124, 433, 435, 437, 584, 587 |
| DCOPY | Disk copy utility | Most disks |
| BOOTCOPY | Boot sector copy | 124, 432, 433, 435, 437, 584, 587 |
| UDCCALC | User-defined character calc | 124, 432, 433, 437, 584, 587 |
| FIXLABEL | Fix disk label | 124, 432, 433, 584, 587 |

## Notes

- Most disks are German language variants (Deutsch keyboard/charset)
- 91.img is a unique games disk with its own boot menu
- 435.img contains WordStar word processor (WS.CMD, WSMSGS.OVR)
- 438.img contains speech synthesis software (SPEAK.CMD, WSPEAK.CMD)
- 584.img and 587.img appear to be similar development environments
