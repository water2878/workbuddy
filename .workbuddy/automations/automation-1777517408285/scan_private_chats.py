"""深度扫描私聊 - 输出JSON供AI主动对话"""
import requests, json, re, os, time, sys
from datetime import datetime

BASE = 'http://127.0.0.1:5031'
TOKEN = 'eaf98e9bc0c13ea0c8e7cf0b29586669'

SKIP_USERNAMES = {
    'wxid_w9c0bfuj8nw212',   # A畅腾升降桌09
    'wxid_anahkoom2m6222',   # A智能升降桌李生
    'mmo9cq806ISzTTg_6oOmLeqOppkpeg@weclaw',  # 贾维斯
}
SKIP_NICKS = {'贾维斯', '文件传输助手', 'filehelper'}

HIGH_KW = ['下单','合同','付款','发货','定了','确定','安排','急','明天','尽快','就这个','可以','成交','定了就','那就']
MEDIUM_KW = ['报价','多少钱','价格','考虑','推荐','合适','优惠','便宜','样品','采购','批发','买几套','要多少','怎么卖','给个价','报个价','什么价','升降桌','办公桌','电动','电机','钢架','面板','T521','T523','T524','T621','T412','T423','T728','手摇']

# 危险信号：系统乱回复、客户困惑
CONFUSION_KW = ['你是谁','你是','系统','机器人','AI','自动回复','怎么不回','不回复','不在','又这样','什么情况']
ANGRY_KW = ['不对','不行','错了','搞什么','太慢','无语','算了','拜拜']

def api_get(endpoint, params):
    params['access_token'] = TOKEN
    return requests.get(f'{BASE}{endpoint}', params=params, timeout=60).json()

data = api_get('/api/v1/sessions', {'limit': 500})
privates = [s for s in data['sessions'] if s['sessionType'] == 'private']

results = []
for s in privates:
    uid = s.get('username', '')
    nick = s.get('displayName', '') or uid[:20]
    
    if uid in SKIP_USERNAMES or nick in SKIP_NICKS:
        continue
    
    try:
        resp = api_get('/api/v1/messages', {
            'talker': uid, 'limit': 500,
            'start': '20260101', 'end': '20991231'
        })
        msgs = resp.get('messages', [])
    except Exception:
        continue
    
    time.sleep(0.3)
    
    if not msgs:
        continue
    
    # 解析消息
    cust = [m for m in msgs if m.get('isSend') == 0 and m.get('content')]
    our = [m for m in msgs if m.get('isSend') == 1 and m.get('content')]
    
    cust_text = [m.get('content','') for m in cust if not m.get('content','').startswith('<')]
    our_text = [m.get('content','') for m in our if not m.get('content','').startswith('<')]
    
    cust_all = ' '.join(cust_text)
    all_text = cust_all + ' ' + ' '.join(our_text)
    
    # === 深度分析 ===
    
    # 1. 意向
    high = sum(1 for k in HIGH_KW if k in cust_all)
    medium = sum(1 for k in MEDIUM_KW if k in all_text)
    
    if high >= 3: intent = '高'
    elif high >= 1 or medium >= 4: intent = '中'
    elif medium >= 1: intent = '低'
    else: intent = '无'
    
    # 2. 客户情绪
    confusion = sum(1 for k in CONFUSION_KW if k in cust_all)
    anger = sum(1 for k in ANGRY_KW if k in cust_all)
    mood = '⚠️困惑' if confusion >= 2 else ('😡不满' if anger >= 2 else '正常')
    
    # 3. 最后实质性对话（非系统测试、非你好）
    real_msgs = [m for m in cust if m.get('content','').strip() 
                 and len(m.get('content','')) > 2
                 and m.get('content','') not in ['你好','您好','在吗','在？','你是','你是谁','1','2','3']]
    
    last_real_ts = 0
    last_real_text = ''
    for m in real_msgs:
        t = m.get('createTime', 0)
        if t > last_real_ts:
            last_real_ts = t
            last_real_text = m.get('content','')[:80]
    
    days_since_real = 999
    if last_real_ts:
        days_since_real = (datetime.now() - datetime.fromtimestamp(last_real_ts)).days
    
    # 4. 时间线
    ts = s.get('lastTimestamp', 0)
    last_dt = datetime.fromtimestamp(ts) if ts else None
    days_total = (datetime.now() - last_dt).days if last_dt else 999
    
    # 最近一条对方消息
    last_cust = cust_text[-1][:60] if cust_text else ''
    
    # 5. 提取型号和数量
    models = set()
    for kw in ['T521','T523','T524','T621','T412','T423','T728']:
        if kw in all_text:
            models.add(kw)
    qty_matches = re.findall(r'(\d+)\s*套', all_text)
    quantities = [int(q) for q in qty_matches if 1 < int(q) < 10000]
    
    # 6. 判断是否需要主动聊
    need_chat = False
    chat_reason = ''
    
    if mood != '正常' and days_since_real <= 7:
        need_chat = True
        chat_reason = f'客户情绪{mood}，需挽回信任'
    elif intent in ('高','中') and days_since_real >= 3:
        need_chat = True
        chat_reason = f'{intent}意向 {days_since_real}天无实质对话'
    elif intent in ('高','中') and days_since_real >= 1:
        need_chat = True
        chat_reason = f'{intent}意向客户，需持续跟进'
    elif models and days_total >= 7:
        need_chat = True
        chat_reason = f'曾咨询{models}，{days_total}天未联系'
    
    results.append({
        'nick': nick,
        'uid': uid,
        'intent': intent,
        'mood': mood,
        'days_total': days_total,
        'days_since_real': days_since_real,
        'total_msgs': len(msgs),
        'cust_msgs': len(cust),
        'high_kw': high,
        'med_kw': medium,
        'models': list(models),
        'quantities': quantities,
        'last_cust': last_cust,
        'last_real': last_real_text,
        'last_ts': last_dt.strftime('%m-%d %H:%M') if last_dt else '未知',
        'need_chat': need_chat,
        'chat_reason': chat_reason,
        'confusion': confusion,
        'anger': anger
    })

# 排序：需要聊的排前面
results.sort(key=lambda r: (not r['need_chat'], -r['days_total']))

# 输出JSON
print(json.dumps({
    'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
    'total_private': len(privates),
    'with_messages': len(results),
    'need_chat': len([r for r in results if r['need_chat']]),
    'results': results
}, ensure_ascii=False, indent=2))
