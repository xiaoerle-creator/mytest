#!/usr/bin/env python3
"""
为定心卷（questions_data_new.js）批量生成六板块 aiExpansion
与白金卷脚本逻辑相同，只是操作的是 QUESTIONS_DB_NEW 和独立的缓存文件
用法: python3 upgrade_dingxin_six_sections.py
"""

import json
import time
import os
import sys
import urllib.request
import urllib.error

# ─── 配置 ─────────────────────────────────
API_KEY = 'sk-315ac0056e0b4d46a279dfc738195202'
BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
MODEL = 'qwen-turbo'
REQUESTS_PER_SEC = 2
CHECKPOINT_FILE = 'upgrade_dingxin_cache.json'
# ───────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'questions_data_new.js')
CHECKPOINT_PATH = os.path.join(BASE_DIR, CHECKPOINT_FILE)

NEW_FORMAT_MARKER = '【📚 核心知识梳理】'


def load_questions():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    # 找到变量声明后的 {
    start = content.index('{')
    json_str = content[start:].rstrip()
    if json_str.endswith(';'):
        json_str = json_str[:-1]
    return json.loads(json_str)


def save_questions(db):
    output = 'const QUESTIONS_DB_NEW = ' + json.dumps(db, ensure_ascii=False, separators=(',', ':')) + ';\n'
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        f.write(output)
    size_mb = os.path.getsize(DATA_FILE) / (1024 * 1024)
    print(f'   ✅ 已写入 {DATA_FILE}（{size_mb:.1f}MB）')


def load_cache():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def is_new_format(text):
    if not text:
        return False
    return NEW_FORMAT_MARKER in text or '【关联考点】' in text


def build_six_section_prompt(q):
    options_str = '；'.join([f"{o['key']}. {o['text']}" for o in (q.get('options') or [])])
    multi = q.get('isMulti', False)
    answer = q.get('answer', '')
    if isinstance(answer, str) and len(answer) > 1 and multi:
        answer_display = '、'.join(list(answer))
    else:
        answer_display = answer

    context_str = ''
    if q.get('context'):
        context_str = f"\n案例背景：{q['context']}"

    return f"""你是口腔医学中级考试（主治医师）辅导专家。请将以下考题的知识点扩展为六个板块，帮助考生深度学习。

题目：{q['question']}{context_str}
题型：{'X型题（多选题）' if multi else 'A型题（单选题）'}
正确答案：{answer_display}
选项：{options_str}
解析：{q.get('explanation') or '无'}

请严格按以下格式输出（每个板块用【标题】开头，板块之间用空行分隔）：

【📚 核心知识梳理】
（200-300字）系统讲解本题涉及的核心知识点，条理清晰，涵盖关键概念和机制。

【🔗 关联考点】
（150-250字）列出3-5个与本题相关的常考知识点，用①②③④编号，每个2-3句话说明。

【⚡ 易错警示】
（100-150字）指出本题最常见的错误思路和易混淆点。

【🏥 临床思维】
（100-150字）将知识点与临床实际场景结合，说明在临床中如何应用。

【💡 记忆口诀】
（1-2句话）朗朗上口的记忆口诀或助记技巧。

【📝 模拟自测】
（150-200字）出2-3道相关的小测验题，每题用①②③编号，格式为"题目？→ 答案"。

要求：
1. 内容必须准确、专业，符合口腔医学中级考试大纲
2. 字数适中，不要过于冗长
3. 只输出六个板块的内容，不要有任何其他文字
4. 科目是{q.get('subject', '口腔医学')}"""


def call_api(prompt):
    body = json.dumps({
        'model': MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 2000,
        'temperature': 0.7
    }).encode('utf-8')

    req = urllib.request.Request(
        BASE_URL,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {API_KEY}'
        },
        method='POST'
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                text = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                return text.strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 10 * (attempt + 1)
                print(f'\n    ⚠️ 限速429，等待{wait}秒...')
                time.sleep(wait)
                continue
            elif e.code == 400:
                body_text = e.read().decode('utf-8', errors='replace')
                print(f'\n    ❌ 400错误: {body_text[:300]}')
                return None
            else:
                body_text = e.read().decode('utf-8', errors='replace')
                print(f'\n    ❌ HTTP {e.code}: {body_text[:200]}')
                return None
        except Exception as e:
            print(f'\n    ❌ 错误: {e}')
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            return None
    return None


def clean_response(text):
    if text.startswith('```'):
        lines = text.split('\n')
        lines = [l for l in lines if not l.strip().startswith('```')]
        text = '\n'.join(lines)
    return text.strip()


def main():
    target_subjects = None
    if len(sys.argv) > 1:
        target_subjects = sys.argv[1:]
        print(f'🎯 指定科目: {", ".join(target_subjects)}')

    print('=' * 60)
    print('  口腔医学定心卷 - 六板块AI扩展生成工具')
    print(f'  模型: {MODEL}')
    print('=' * 60)

    print('\n📂 加载定心卷题库...')
    db = load_questions()
    total = sum(len(qs) for qs in db.values())
    print(f'   共 {total} 道题目')

    cache = load_cache()
    print(f'   已处理缓存 {len(cache)} 道')

    need_upgrade = []
    for subject, questions in db.items():
        if target_subjects and subject not in target_subjects:
            continue
        for q in questions:
            qid = q['id']
            if is_new_format(q.get('aiExpansion', '')):
                continue
            if qid in cache:
                continue
            need_upgrade.append((subject, q))

    print(f'   需要生成: {len(need_upgrade)} 道')

    if not need_upgrade:
        print('\n✅ 所有题目已有六板块内容或已处理！')
        for subject, questions in db.items():
            for q in questions:
                qid = q['id']
                if qid in cache:
                    q['aiExpansion'] = cache[qid]
        save_questions(db)
        return

    subject_counts = {}
    for subj, q in need_upgrade:
        subject_counts[subj] = subject_counts.get(subj, 0) + 1
    print('\n📊 各科目待处理:')
    for subj, cnt in sorted(subject_counts.items()):
        print(f'   {subj}: {cnt} 题')

    print(f'\n🚀 开始批量生成（限速 {REQUESTS_PER_SEC} 次/秒）...\n')

    interval = 1.0 / REQUESTS_PER_SEC
    success = 0
    failed = 0

    for i, (subject, q) in enumerate(need_upgrade):
        qid = q['id']
        progress = f'[{i+1}/{len(need_upgrade)}]'

        print(f'{progress} {qid}', end='', flush=True)

        prompt = build_six_section_prompt(q)
        result = call_api(prompt)

        if result and len(result) > 50:
            result = clean_response(result)
            if '核心知识梳理' in result and '关联考点' in result:
                cache[qid] = result
                success += 1
                print(f' ✅ ({len(result)}字)')
            else:
                print(f' ⚠️ 格式不完整，跳过')
                failed += 1
        else:
            failed += 1
            print(f' ❌')

        if (i + 1) % 20 == 0:
            save_cache(cache)
            print(f'   💾 已保存缓存（{len(cache)}条）')

        time.sleep(interval)

    save_cache(cache)

    print(f'\n{"=" * 60}')
    print(f'  完成！成功: {success}，失败: {failed}')
    print(f'  缓存: {CHECKPOINT_PATH}')
    print(f'{"=" * 60}')

    for subject, questions in db.items():
        for q in questions:
            qid = q['id']
            if qid in cache:
                q['aiExpansion'] = cache[qid]

    save_questions(db)

    print('\n🔍 验证JSON合法性...')
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        start = content.index('{')
        json_str = content[start:].rstrip()
        if json_str.endswith(';'):
            json_str = json_str[:-1]
        json.loads(json_str)
        print('   ✅ JSON验证通过！')
    except json.JSONDecodeError as e:
        print(f'   ❌ JSON错误: {e}')


if __name__ == '__main__':
    main()
