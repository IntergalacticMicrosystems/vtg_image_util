# IBM PC Floppy Disk Formats, Boot Sectors, and FAT Layouts  
### Reference Overview for LLMs  
**Covers:** 360 KB, 720 KB, 1.2 MB, 1.44 MB IBM-PC DOS floppy disk formats  
**Focus:** Geometry, boot sector structure, BPB fields, FAT12 layout, directory structure, quirks, and historical compatibility

## 1. Introduction

The IBM PC platform used **FAT12** for all standard floppy disk formats from the original 360 KB 5¼″ media through high-density 1.44 MB 3½″ media.  
Although the FAT12 filesystem is simple, real-world disks vary in geometry and BPB fields depending on DOS version, OEM vendor, and media type.

This document summarizes the **physical formats**, **logical filesystem structures**, and **boot sector details** for the canonical MS-DOS/PC-DOS compatible floppy formats.

---

# 2. Standard IBM PC Floppy Disk Formats

## 2.1 Format Comparison Table

| Media Size | Capacity | Sides | Tracks | Sectors/Track | Bytes/Sector | Data Rate | FAT Type |
|-----------|----------|-------|--------|----------------|--------------|-----------|----------|
| **5¼″ DD** | **360 KB** | 2 | 40 | 9 | 512 | 250 kbps | FAT12 |
| **3½″ DD** | **720 KB** | 2 | 80 | 9 | 512 | 250 kbps | FAT12 |
| **5¼″ HD** | **1.2 MB** | 2 | 80 | 15 | 512 | 500 kbps | FAT12 |
| **3½″ HD** | **1.44 MB** | 2 | 80 | 18 | 512 | 500 kbps | FAT12 |

---

# 3. Boot Sector Structure

Every FAT12 floppy contains a **boot sector at LBA 0** (CHS 0/0/1).  
The boot sector includes:
- Jump instruction  
- OEM string  
- BIOS Parameter Block (BPB)  
- Extended BPB (DOS 4+)  
- Bootstrap code  
- Signature `0x55AA`

---

# 4. FAT12 BIOS Parameter Block (BPB)

## 4.1 Standard BPB Layout

| Offset | Size | Field |
|--------|------|--------|
| 0x00 | 3 | Jump |
| 0x03 | 8 | OEMName |
| 0x0B | 2 | BytesPerSector |
| 0x0D | 1 | SecPerCluster |
| 0x0E | 2 | ReservedSectors |
| 0x10 | 1 | NumFATs |
| 0x11 | 2 | RootEntryCount |
| 0x13 | 2 | TotalSectors16 |
| 0x15 | 1 | MediaDescriptor |
| 0x16 | 2 | FATSize16 |
| 0x18 | 2 | SecPerTrack |
| 0x1A | 2 | NumHeads |
| 0x1C | 4 | HiddenSectors |
| 0x20 | 4 | TotalSectors32 |

---

# 5. FAT12 Filesystem Layout

```
Boot Sector
FAT #1
FAT #2
Root Directory
Data Area (clusters)
```

---

# 6. Detailed Geometry for Each Format

## 6.1 360 KB (5¼″ DD)
- 40 tracks, 2 sides, 9 sectors/track  
- 720 sectors  
- Sec/Cluster = 2  
- Media = F9  

## 6.2 720 KB (3½″ DD)
- 80 tracks, 2 sides, 9 sectors/track  
- 1440 sectors  
- Sec/Cluster = 2  
- Media = F9  

## 6.3 1.2 MB (5¼″ HD)
- 80 tracks, 2 sides, 15 sectors/track  
- 2400 sectors  
- Sec/Cluster = 1  
- Media = F9  

## 6.4 1.44 MB (3½″ HD)
- 80 tracks, 2 sides, 18 sectors/track  
- 2880 sectors  
- Sec/Cluster = 1  
- Media = F0  

---

# 7. FAT12 Details

## 7.1 12‑bit FAT Entry Encoding

```
Entry N and N+1 packed into 3 bytes:
Byte0 = low 8 bits of N
Byte1 = high 4 bits of N + low 4 bits of N+1
Byte2 = high 8 bits of N+1
```

Special values: free, bad cluster, end-of-chain, etc.

---

# 8. Boot Code Notes

Most disks contain minimal boot code loading IO.SYS/MSDOS.SYS.  
Non-bootable disks still contain message stubs.

---

# 9. Compatibility Notes

- 360 KB disks written in 1.2 MB drives may be hard to read in DD drives  
- USB floppy drives hardcode 1.44 MB geometry  
- Older DOS versions used reduced BPB fields  

---

# 10. 1.44 MB Layout Summary

```
Sector 0   Boot sector
1–9        FAT #1
10–18      FAT #2
19–32      Root directory
33–2879    Data area
```

