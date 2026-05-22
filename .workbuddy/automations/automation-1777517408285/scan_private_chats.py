"""拉取私聊列表供AI判断——不预设跳过规则，由AI现场判谁内谁外"""
import requests, json, re, os, sys, time
from datetime import datetime, timedelta

BASE = 'http://127.0.0.1:5031'
TOKEN = 'eaf98e9bc0c13ea0c8e7cf0b29586669'
COOLDOWN_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'proactive_chat_log.json')
COOLDOWN_DAYS = 30

# 只有三个绝对不可能是客户的
ABSOLUTE_SKIP = {
    'wxid_anahkoom2m6222',   # 自己的微信号
    'wxid_w9c0bfuj8nw212',   # A畅腾升降桌09
    'mmo9cq806ISzTTg_6oOmLeqOppkpeg@weclaw',  # 贾维斯
}

HIGH_KW = ['下单','合同','付款','发货','定了','确定','安排','急','尽快','就这个','成交','定了就','那就']
MEDIUM_KW = ['报价','多少钱','价格','考虑','推荐','合适','优惠','便宜','样品','采购','批发','买几套','要多少','怎么卖','报个价','什么价','升降桌','办公桌','电动','电机','钢架','面板','T521','T523','T524','T621','T412','T423','T728','手摇']

def api_get(endpoint, params):
    params['access_token'] = TOKEN
    return requests.get(f'{BASE}{endpoint}', params=params, timeout=60).json()

def load_cooldown():
    if os.path.exists(COOLDOWN_FILE):
        with open(COOLDOWN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def mark_sent(nickname):
    log = load_cooldown()
    log[nickname] = datetime.now().strftime('%Y-%m-%d %H:%M')
    os.makedirs(os.path.dirname(COOLDOWN_FILE), exist_ok=True)
    with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

# --mark-sent
if '--mark-sent' in sys.argv:
    idx = sys.argv.index('--mark-sent')
    if idx + 1 < len(sys.argv):
        mark_sent(sys.argv[idx + 1])
        print(json.dumps({'marked': sys.argv[idx + 1]}, ensure_ascii=False))
        sys.exit(0)

# --get-messages 昵称: 拉指定客户的消息
if '--get-messages' in sys.argv:
    idx = sys.argv.index('--get-messages')
    if idx + 1 < len(sys.argv):
        nick = sys.argv[idx + 1]
        # 先找 uid
        data = api_get('/api/v1/sessions', {'limit': 500})
        uid = None
        for s in data['sessions']:
            if s.get('displayName') == nick:
                uid = s.get('username')
                break
        if uid:
            today = datetime.now().strftime('%Y%m%d')
            ago = (datetime.now() - timedelta(days=120)).strftime('%Y%m%d')
            resp = api_get('/api/v1/messages', {'talker': uid, 'limit': 50, 'start': '20260101', 'end': '20991231'})
            msgs = resp.get('messages', [])
            # 只输出文本消息
            lines = []
            for m in msgs:
                side = '客户' if m.get('isSend') == 0 else '我'
                ct = m.get('content', '')[:200]
                if ct and not ct.startswith('<'):
                    t = m.get('createTime', 0)
                    dt = datetime.fromtimestamp(t).strftime('%m-%d %H:%M') if t else ''
                    lines.append(f'[{dt}] {side}: {ct}')
            print(json.dumps({'nick': nick, 'uid': uid, 'msg_count': len(msgs), 'messages': lines[-50:]}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({'error': f'未找到 {nick}'}, ensure_ascii=False))
        sys.exit(0)

# 主流程：输出所有私聊供AI判断
data = api_get('/api/v1/sessions', {'limit': 500})
privates = [s for s in data['sessions'] if s['sessionType'] == 'private']

now = datetime.now()
cutoff_30d = int((now - timedelta(days=30)).timestamp())
cooldown = load_cooldown()

all_contacts = []
for s in privates:
    uid = s.get('username', '')
    nick = s.get('displayName', '') or uid[:20]
    ts = s.get('lastTimestamp', 0)
    
    if uid in ABSOLUTE_SKIP:
        continue
    
    last_dt = datetime.fromtimestamp(ts).strftime('%m-%d %H:%M') if ts else '未知'
    days = (now - datetime.fromtimestamp(ts)).days if ts else 999
    inactive_1m = ts < cutoff_30d
    in_cd = nick in cooldown
    
    # 快速拉最近10条看有没有产品关键词
    intent_hint = ''
    if ts > 0:
        try:
            resp = api_get('/api/v1/messages', {'talker': uid, 'limit': 30, 'start': '20260101', 'end': '20991231'})
            msgs = resp.get('messages', [])
            time.sleep(0.2)
            
            if msgs:
                cust_text = ' '.join([m.get('content','') for m in msgs 
                                       if m.get('isSend')==0 and m.get('content','') and not m.get('content','').startswith('<')])
                all_text = cust_text + ' ' + ' '.join([m.get('content','') for m in msgs 
                                       if m.get('isSend')==1 and m.get('content','') and not m.get('content','').startswith('<')])
                
                high = sum(1 for k in HIGH_KW if k in cust_text)
                medium = sum(1 for k in MEDIUM_KW if k in all_text)
                models = [kw for kw in ['T521','T523','T524','T621','T412','T423','T728'] if kw in all_text]
                
                if high >= 2: intent_hint = '🔥高意向'
                elif high >= 1 or medium >= 3: intent_hint = '🟡有产品兴趣'
                elif medium >= 1: intent_hint = '⚪浅度'
                
                # 最后客户消息
                last_cust = ''
                for m in reversed(msgs):
                    if m.get('isSend')==0 and m.get('content','') and not m.get('content','').startswith('<'):
                        last_cust = m.get('content','')[:60]
                        break
        except:
            pass
    
    all_contacts.append({
        'nick': nick,
        'uid': uid,
        'last': last_dt,
        'days': days,
        'inactive_1m': inactive_1m,
        'intent_hint': intent_hint,
        'last_cust': last_cust if 'last_cust' in dir() else '',
        'cooldown': in_cd
    })

# 排序：不活跃的排前面
all_contacts.sort(key=lambda c: (-c['inactive_1m'], -c['days']))

print(json.dumps({
    'scan_time': now.strftime('%Y-%m-%d %H:%M'),
    'total': len(all_contacts),
    'active': len([c for c in all_contacts if not c['inactive_1m']]),
    'inactive_1m': len([c for c in all_contacts if c['inactive_1m']]),
    'contacts': all_contacts
}, ensure_ascii=False, indent=2))
