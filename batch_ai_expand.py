#!/usr/bin/env python3
"""
批量调用千问API为所有题目生成知识点扩展，结果写入 questions_data.js
用法: python3 batch_ai_expand.py
- 首次运行会生成所有785题的扩展
- 支持断点续传（已有 aiExpansion 的题目会跳过）
- API限速：每秒2次请求，遇429自动等待
"""

import json
import time
import os
import sys
import urllib.request
import urllib.error

# ─── 配置 ─────────────────────────────────
API_KEY = 'sk-315ac0056e0b4d46a279dfc738195202'
BASE_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation'
MODEL = 'qwen-turbo'
REQUESTS_PER_SEC = 2  # 限速
CHECKPOINT_FILE = 'ai_expansion_cache.json'  # 断点续传缓存
# ───────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'questions_data.js')
CHECKPOINT_PATH = os.path.join(BASE_DIR, CHECKPOINT_FILE)


def load_questions():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    start = content.index('{')
    json_str = content[start:].rstrip()
    if json_str.endswith(';'):
        json_str = json_str[:-1]
    return json.loads(json_str)


def load_cache():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def call_qwen(prompt):
    """调用千问API，返回文本结果"""
    body = json.dumps({
        'model': MODEL,
        'input': {
            'messages': [{'role': 'user', 'content': prompt}]
        },
        'parameters': {
            'max_tokens': 500,
            'temperature': 0.7
        }
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
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                text = data.get('output', {}).get('text', '') or \
                       data.get('output', {}).get('choices', [{}])[0].get('message', {}).get('content', '')
                return text.strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 10 * (attempt + 1)
                print(f'    ⚠️ 限速429，等待{wait}秒...')
                time.sleep(wait)
                continue
            else:
                body_text = e.read().decode('utf-8', errors='replace')
                print(f'    ❌ HTTP {e.code}: {body_text[:200]}')
                return None
        except Exception as e:
            print(f'    ❌ 错误: {e}')
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            return None
    return None


def build_prompt(q):
    """构建AI prompt，与APP中的prompt保持一致"""
    options_str = '；'.join([f"{o['key']}. {o['text']}" for o in (q.get('options') or [])])
    multi = q.get('isMulti', False)
    answer = q.get('answer', '')
    if isinstance(answer, str) and len(answer) > 1 and multi:
        answer_display = '、'.join(list(answer))
    else:
        answer_display = answer

    return f"""你是口腔医学专家，请针对以下考题，用简洁清晰的语言深度解析知识点，帮助医学生记忆和理解。

题目：{q['question']}{'案例背景：' + q['context'] if q.get('context') else ''}
题型：{'X型题（多选题）' if multi else 'A型题（单选题）'}
正确答案：{answer_display}
选项内容：{options_str}
解析：{q.get('explanation') or '无'}

请从以下角度展开解析（200字以内）：
1. 核心知识点总结
2. {'各选项逐一分析（为什么选/不选）' if multi else '易混淆点提醒'}
3. 记忆技巧或口诀

直接输出分析内容，不要有多余格式。"""


def main():
    print('=' * 60)
    print('  口腔医学刷题 - AI知识点批量扩展工具')
    print(f'  模型: {MODEL}')
    print('=' * 60)

    # 加载数据
    print('\n📂 加载题库...')
    db = load_questions()
    total = sum(len(qs) for qs in db.values())
    print(f'   共 {total} 道题目')

    # 加载缓存
    cache = load_cache()
    cached_count = len(cache)
    print(f'   已缓存 {cached_count} 道扩展')

    # 统计需要处理的题目
    need_process = []
    for subject, questions in db.items():
        for q in questions:
            qid = q['id']
            if qid not in cache and not q.get('aiExpansion'):
                need_process.append(q)

    if not need_process:
        print('\n✅ 所有题目已有扩展，无需处理！')
        write_results(db, cache)
        return

    print(f'   待处理 {len(need_process)} 道')
    print(f'\n🚀 开始批量生成（限速 {REQUESTS_PER_SEC} 次/秒）...\n')

    interval = 1.0 / REQUESTS_PER_SEC
    success = 0
    failed = 0

    for i, q in enumerate(need_process):
        qid = q['id']
        progress = f'[{i+1}/{len(need_process)}]'

        print(f'{progress} {qid}', end='', flush=True)

        prompt = build_prompt(q)
        result = call_qwen(prompt)

        if result and len(result) > 10:
            cache[qid] = result
            success += 1
            print(f' ✅ ({len(result)}字)')
        else:
            failed += 1
            print(f' ❌')

        # 每50题保存一次缓存
        if (i + 1) % 50 == 0:
            save_cache(cache)
            print(f'   💾 已保存缓存（{len(cache)}条）')

        # 限速
        time.sleep(interval)

    # 最终保存缓存
    save_cache(cache)

    print(f'\n{"=" * 60}')
    print(f'  ✅ 完成！成功: {success}，失败: {failed}')
    print(f'  缓存已保存: {CHECKPOINT_PATH}')
    print(f'{"=" * 60}')

    # 写入题库文件
    write_results(db, cache)


def write_results(db, cache):
    """将AI扩展写入 questions_data.js"""
    print('\n📝 写入题库文件...')

    # 将缓存中的扩展合并到题目数据
    for subject, questions in db.items():
        for q in questions:
            qid = q['id']
            if qid in cache:
                q['aiExpansion'] = cache[qid]

    # 生成新的JS文件
    output = 'const QUESTIONS_DB = ' + json.dumps(db, ensure_ascii=False, separators=(',', ':')) + ';\n'

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        f.write(output)

    size_mb = os.path.getsize(DATA_FILE) / (1024 * 1024)
    print(f'   ✅ 已写入 {DATA_FILE}（{size_mb:.1f}MB）')


if __name__ == '__main__':
    main()
