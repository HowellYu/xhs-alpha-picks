#!/usr/bin/env python3
"""Test script to verify Chinese text encoding in .txt files."""

from pathlib import Path
from datetime import datetime

# Test content with Chinese characters
test_content = f"""Alpha Picks Summary - 2025-10-31
================================================================================
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Number of Notes: 2
--------------------------------------------------------------------------------

Note 1:
  Note ID: test123
  Title: 测试Alpha Picks 2025-10-31新增企业
  Author: 测试作者
  Selection Date: 2025-10-31
  Publish Time: 2025-10-31 12:00:00
  URL: https://www.xiaohongshu.com/explore/test123
  Quality Score: 0.90
  High Quality: True
  Quality Notes: 包含多个选择, 有日期, 有Seeking Alpha引用

  Post Text:
  ----------------------------------------------------------------------------
  这是测试帖子文本
  今天Alpha Picks新增了三家公司：
  1. AAPL - 苹果公司
  2. TSLA - 特斯拉
  3. MSFT - 微软

  推荐理由：这些都是优质科技股。
  
  Post text with English: This is a test post about Alpha Picks selections.

  OCR Text (from images):
  ----------------------------------------------------------------------------
  OCR文本内容：
  Seeking Alpha Picks 2025-10-31
  新增企业：
  - AAPL (Apple Inc.) - Buy推荐
  - TSLA (Tesla Inc.) - Hold
  - MSFT (Microsoft) - Strong Buy
  
  Alpha Picks新增企业推荐表
  日期：2025年10月31日
  
  OCR text with English: Alpha Picks selection table from images.

Note 2:
  Note ID: test456
  Title: Alpha Picks 2025-09-15 removed companies
  Author: 另一个作者
  Selection Date: 2025-09-15
  Publish Time: 2025-09-15 15:30:00
  URL: https://www.xiaohongshu.com/explore/test456
  Quality Score: 0.85
  High Quality: True
  Quality Notes: 包含移除公司信息

  Post Text:
  ----------------------------------------------------------------------------
  今日Alpha Picks移除的企业：
  - NVDA (英伟达) - 已卖出
  - META (Meta Platforms) - 持仓调整
  
  Post in English: Today Alpha Picks removed some companies from the portfolio.

  OCR Text (from images):
  ----------------------------------------------------------------------------
  移除企业列表：
  2025-09-15
  NVDA - Sold
  META - Position adjustment
  
  原因：市场变化和技术面分析
  
  OCR English: Removed companies list with reasons.

================================================================================
"""

# Test different encoding methods
test_files = {
    "utf8": ("test_chinese_utf8.txt", "utf-8"),
    "utf8_bom": ("test_chinese_utf8_bom.txt", "utf-8-sig"),
    "utf8_no_bom": ("test_chinese_utf8_no_bom.txt", "utf-8"),
}

print("Creating test files with Chinese text...\n")

for name, (filename, encoding) in test_files.items():
    filepath = Path(filename)
    
    with open(filepath, "w", encoding=encoding, newline="\n") as f:
        f.write(test_content)
    
    # Check file encoding
    import subprocess
    result = subprocess.run(
        ["file", str(filepath)],
        capture_output=True,
        text=True,
    )
    
    file_size = filepath.stat().st_size
    print(f"{name.upper()} ({encoding}):")
    print(f"  File: {filename}")
    print(f"  Size: {file_size} bytes")
    print(f"  Encoding: {result.stdout.strip()}")
    
    # Show first few bytes (BOM check)
    with open(filepath, "rb") as f:
        first_bytes = f.read(10)
        hex_repr = " ".join(f"{b:02x}" for b in first_bytes)
        print(f"  First 10 bytes (hex): {hex_repr}")
        if first_bytes[:3] == b"\xef\xbb\xbf":
            print(f"  → Has UTF-8 BOM (EF BB BF)")
        else:
            print(f"  → No BOM")
    print()

print("Test files created!")
print("\nPlease try opening these files in your macOS text editor:")
for name, (filename, _) in test_files.items():
    print(f"  - {filename}")
print("\nWhich one opens correctly without encoding errors?")

