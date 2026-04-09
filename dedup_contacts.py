# -*- coding: utf-8 -*-
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
"""
微信联系人昵称去重清洗
- 全角转半角统一比较
- 括号统一为半角
- 去除前导数字噪声（如 '1冯玉鹏'）
- 过滤残缺片段（长度<=2且无中文、纯符号行）
- 精确重复 + 归一化重复 均去除
"""
import re

INPUT_FILE  = r"C:\Users\Lenovo\Desktop\微信联系人昵称.txt"
OUTPUT_FILE = r"C:\Users\Lenovo\Desktop\微信联系人昵称.txt"  # 原地覆盖


def normalize(s: str) -> str:
    """归一化：全角→半角、括号统一、去首尾空格、去标点、小写"""
    r = ""
    for c in s:
        cp = ord(c)
        if 0xFF01 <= cp <= 0xFF5E:
            r += chr(cp - 0xFEE0)
        elif c == "\u3000":
            r += " "
        else:
            r += c
    r = r.replace("（", "(").replace("）", ")")
    # 去前导数字噪声，如 "1冯玉鹏" → "冯玉鹏"、"个响港" → "响港"
    r = re.sub(r"^\d+(?=[^\d])", "", r.strip())
    r = re.sub(r"^[个各](?=[\u4e00-\u9fff])", "", r)   # 前导误字"个/各"
    # 去掉末尾纯数字/纯标点残留
    r = re.sub(r"[\s\-~·•。，！？\.]+$", "", r)
    return r.strip().lower()


def edit_distance(a: str, b: str) -> int:
    """计算两个字符串的编辑距离"""
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            tmp = dp[j]
            dp[j] = prev if a[i-1] == b[j-1] else 1 + min(prev, dp[j], dp[j-1])
            prev = tmp
    return dp[lb]


def is_fragment(t: str) -> bool:
    """判断是否为明显残缺/噪声行"""
    t = t.strip()
    if not t:
        return True
    # 只有1个字符（中文或其他）
    if len(t) == 1:
        return True
    # 长度<=3 且无中文，且不是纯英文单词（如 XMX naa1）
    if len(t) <= 2 and not re.search(r"[\u4e00-\u9fff]", t):
        return True
    # 全是括号/空格/符号
    if re.fullmatch(r"[（）()\[\]{}\u300c\u300d\u3010\u3011\s\-~·•°℃]+", t):
        return True
    # 纯标点开头+1~2字（如"（畅腾）"这种括号包裹的残片）
    if re.fullmatch(r"[（(（].{1,4}[)）]", t):
        return True
    return False


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        lines = f.read().splitlines()

    # 第一轮：过滤残缺 + 精确/归一化去重
    candidates = []
    seen_norm: dict = {}
    removed = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if is_fragment(line):
            removed.append(f"  [残缺] {line!r}")
            continue
        nk = normalize(line)
        if nk in seen_norm:
            removed.append(f"  [精确重复] {line!r}  ←已有→ {seen_norm[nk]!r}")
        else:
            seen_norm[nk] = line
            candidates.append((line, nk))

    # 第二轮：编辑距离相似去重（阈值=2，只在长度相近时比较）
    kept_idx = list(range(len(candidates)))
    drop = set()
    for i in range(len(candidates)):
        if i in drop:
            continue
        a_raw, a_norm = candidates[i]
        for j in range(i + 1, len(candidates)):
            if j in drop:
                continue
            b_raw, b_norm = candidates[j]
            # 长度差>3 不比较（不可能是OCR误读的同一人）
            if abs(len(a_norm) - len(b_norm)) > 3:
                continue
            # 短串（≤4字）用更严格的阈值
            threshold = 1 if len(a_norm) <= 4 else 2
            dist = edit_distance(a_norm, b_norm)
            if dist <= threshold:
                # 保留较长的（信息量更多）
                keep, drop_one = (i, j) if len(a_raw) >= len(b_raw) else (j, i)
                drop.add(drop_one)
                removed.append(
                    f"  [相似去重 dist={dist}] {candidates[drop_one][0]!r}"
                    f"  ←保留→ {candidates[keep][0]!r}"
                )

    kept = [candidates[i][0] for i in range(len(candidates)) if i not in drop]

    # 输出
    print(f"原始 {len(lines)} 条  →  保留 {len(kept)} 条  （删除 {len(lines)-len(kept)} 条）\n")
    print("删除详情：")
    for r in removed:
        print(r)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for name in kept:
            f.write(name + "\n")

    print(f"\n✅ 已保存到 {OUTPUT_FILE}")
    print(f"\n--- 全部保留昵称（{len(kept)} 个）---")
    for name in kept:
        print(f"  {name}")


if __name__ == "__main__":
    main()
