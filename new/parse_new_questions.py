#!/usr/bin/env python3
"""
解析 new/ 文件夹下的8个定心卷 docx，生成 questions_data_new.js
格式与原 questions_data.js 完全一致，ID 前缀改为 "定心卷" 以区分

支持：
  - 普通单选/多选题
  - 共用题干题（N~M题共用题干）
  - 共用选项题（N~M题共用选项）
"""

import zipfile
import json
import os
import re
from xml.etree import ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(os.path.dirname(BASE_DIR), '刷题APP', 'questions_data_new.js')

# 文件 → (科目, 来源)
FILES = [
    ('353基础知识定心卷1.docx',   '基础知识',     '定心卷1'),
    ('353基础知识定心卷2.docx',   '基础知识',     '定心卷2'),
    ('353相关专业定心卷1.docx',   '相关专业知识', '定心卷1'),
    ('353相关专业定心卷2.docx',   '相关专业知识', '定心卷2'),
    ('353专业知识定心卷1.docx',   '专业知识',     '定心卷1'),
    ('353专业知识定心卷2.docx',   '专业知识',     '定心卷2'),
    ('353专业实践定心卷1.docx',   '专业实践能力', '定心卷1'),
    ('353专业实践定心卷2.docx',   '专业实践能力', '定心卷2'),
]


def extract_docx_text(path):
    """提取 docx 所有段落文本"""
    with zipfile.ZipFile(path) as z:
        with z.open('word/document.xml') as f:
            tree = ET.parse(f)
    root = tree.getroot()
    paras = []
    for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
        texts = []
        for r in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
            if r.text:
                texts.append(r.text)
        line = ''.join(texts).strip()
        paras.append(line)
    return paras


def parse_options(lines, start_i):
    """从 start_i 开始读取选项行，返回 (options列表, 新的i)"""
    options = []
    i = start_i
    while i < len(lines):
        nl = lines[i].strip()
        m_opt = re.match(r'^([A-Fa-f])\s*[：:．.]\s*(.*)$', nl)
        if m_opt:
            opt_key = m_opt.group(1).upper()
            opt_text = m_opt.group(2).strip()
            i += 1
            # 选项文本可能跨行
            while i < len(lines):
                nxt = lines[i].strip()
                if (re.match(r'^[A-Fa-f]\s*[：:．.]', nxt) or
                        re.match(r'^正确答案', nxt) or
                        re.match(r'^\d+\s*[：:]', nxt) or
                        re.match(r'^[（(]\s*\d+', nxt) or
                        not nxt):
                    break
                opt_text += nxt
                i += 1
            options.append({'key': opt_key, 'text': opt_text})
        else:
            break
    return options, i


def parse_questions(lines, subject, source):
    """解析行列表，返回题目列表"""
    questions = []
    current_context = None   # 当前共用题干
    current_shared_opts = None  # 当前共用选项（共用选项题型）
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # ── 共用题干标记 ──────────────────────────────────
        m_ctx_header = re.match(r'[（(]\s*(\d+)\s*[~～]\s*(\d+)\s*题共用题干\s*[）)]', line)
        if m_ctx_header:
            # 清除共用选项（两种块类型互斥）
            current_shared_opts = None
            i += 1
            ctx_lines = []
            while i < len(lines):
                nl = lines[i].strip()
                if re.match(r'^\d+\s*[：:]', nl) or re.match(r'^[（(]\s*\d+', nl):
                    break
                if nl:
                    ctx_lines.append(nl)
                i += 1
            current_context = '\n'.join(ctx_lines) if ctx_lines else None
            continue

        # ── 共用选项标记 ──────────────────────────────────
        m_sopt_header = re.match(r'[（(]\s*(\d+)\s*[~～]\s*(\d+)\s*题共用选项\s*[）)]', line)
        if m_sopt_header:
            # 清除共用题干
            current_context = None
            i += 1
            shared_options, i = parse_options(lines, i)
            current_shared_opts = shared_options
            continue

        # ── 题目行：以"数字："或"数字."开头 ──────────────
        m_q = re.match(r'^(\d+)\s*[：:.]\s*(.+)$', line)
        if m_q:
            q_num = int(m_q.group(1))
            q_text_raw = m_q.group(2).strip()

            i += 1
            # 题干可能跨多行（遇到选项或正确答案才结束）
            extra_lines = []
            while i < len(lines):
                nl = lines[i].strip()
                if (re.match(r'^[A-Fa-f]\s*[：:．.]', nl) or
                        re.match(r'^正确答案', nl) or
                        re.match(r'^\d+\s*[：:]', nl) or
                        re.match(r'^[（(]\s*\d+', nl)):
                    break
                if nl:
                    extra_lines.append(nl)
                else:
                    break
                i += 1
            if extra_lines:
                q_text_raw = q_text_raw + '\n' + '\n'.join(extra_lines)

            # ── 读取选项（如果是共用选项题，小题本身没有选项行）──
            if current_shared_opts is not None:
                # 检查下一行是否是选项（有的题可能重复写了选项）
                options = current_shared_opts
                # 跳过重复的选项行（如果有）
                while i < len(lines):
                    nl = lines[i].strip()
                    if re.match(r'^[A-Fa-f]\s*[：:．.]', nl):
                        i += 1  # 跳过
                    else:
                        break
            else:
                options, i = parse_options(lines, i)

            # ── 读取答案 ──────────────────────────────────
            answer_raw = ''
            while i < len(lines):
                nl = lines[i].strip()
                m_ans = re.match(r'^正确答案\s*[：:]\s*(.+)$', nl)
                if m_ans:
                    answer_raw = m_ans.group(1).strip()
                    i += 1
                    break
                if re.match(r'^\d+\s*[：:]', nl) or re.match(r'^[（(]\s*\d+', nl):
                    break
                i += 1

            # ── 读取解析（可选）──────────────────────────
            explanation = ''
            if i < len(lines):
                nl = lines[i].strip()
                m_exp = re.match(r'^答案解析\s*[：:]\s*(.*)$', nl)
                if m_exp:
                    exp_parts = [m_exp.group(1).strip()]
                    i += 1
                    while i < len(lines):
                        nxt = lines[i].strip()
                        if (re.match(r'^\d+\s*[：:]', nxt) or
                                re.match(r'^[（(]\s*\d+', nxt) or
                                not nxt):
                            break
                        exp_parts.append(nxt)
                        i += 1
                    explanation = '\n'.join(filter(None, exp_parts))

            # ── 判断多选 ──────────────────────────────────
            ans_letters = re.findall(r'[A-Fa-f]', answer_raw)
            is_multi = len(ans_letters) > 1
            answer_str = ''.join(sorted(set(a.upper() for a in ans_letters)))

            # 清理题干：去掉 [第X问] 等前缀标记
            q_text = re.sub(r'^\[第?[一二三四五六七八九十\d]+问\]\s*', '', q_text_raw).strip()

            q_id = f"{subject}_{source}_{q_num}"

            q_obj = {
                'id': q_id,
                'question': q_text,
                'context': current_context,
                'options': options,
                'answer': answer_str,
                'isMulti': is_multi,
                'explanation': explanation,
                'subject': subject,
                'source': source,
                'unit': source,
                'aiExpansion': '',
            }

            questions.append(q_obj)
            continue

        # 其他行跳过
        i += 1

    return questions


def main():
    db = {}

    for filename, subject, source in FILES:
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            print(f'[跳过] 文件不存在: {path}')
            continue
        print(f'解析 {filename} ...')
        lines = extract_docx_text(path)
        qs = parse_questions(lines, subject, source)

        # 统计问题
        no_ans = [q['id'] for q in qs if not q['answer']]
        no_opt = [q['id'] for q in qs if not q['options']]
        print(f'  → {len(qs)} 题  (无答案: {len(no_ans)}, 无选项: {len(no_opt)})')
        if no_ans[:3]:
            print(f'    无答案示例: {no_ans[:3]}')

        if subject not in db:
            db[subject] = []
        db[subject].extend(qs)

    # 统计
    total = sum(len(v) for v in db.values())
    multi_total = sum(1 for qs in db.values() for q in qs if q['isMulti'])
    ctx_total = sum(1 for qs in db.values() for q in qs if q['context'])
    all_no_ans = [q['id'] for qs in db.values() for q in qs if not q['answer']]
    print(f'\n共解析 {total} 题  |  多选: {multi_total}  |  共用题干/选项: {ctx_total}  |  无答案: {len(all_no_ans)}')
    for subj, qs in db.items():
        print(f'  {subj}: {len(qs)} 题')

    # 写出 JS 文件
    js_content = 'const QUESTIONS_DB_NEW = ' + json.dumps(db, ensure_ascii=False, indent=2) + ';\n'
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(js_content)
    print(f'\n已写出: {OUT_FILE}')


if __name__ == '__main__':
    main()
