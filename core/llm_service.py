"""
LLM服务 - 畅腾升降桌客服
基于历史记忆的智能回复生成
"""

import re
from config import log

# 尝试导入 Moonshot API
MOONSHOT_API_KEY = None
MOONSHOT_API_URL = "https://api.moonshot.cn/v1/chat/completions"

try:
    import config
    MOONSHOT_API_KEY = getattr(config, 'MOONSHOT_API_KEY', None)
except:
    pass


def generate_llm_reply(prompt: str, contact: str = "") -> str:
    """
    生成LLM回复
    
    流程：
    1. 解析 prompt 中的记忆和当前消息
    2. 基于记忆内容生成连贯回复
    3. 返回广东风格的简洁回复
    """
    # 解析 prompt 结构
    memory_section = ""
    current_message = ""
    
    if "历史相关记忆：" in prompt:
        parts = prompt.split("客户当前消息：")
        if len(parts) >= 2:
            memory_section = parts[0].split("历史相关记忆：")[-1].strip()
            current_message = parts[1].split("\n")[0].strip()
    else:
        current_message = prompt
    
    msg_lower = current_message.lower()
    
    # --- 基于记忆的智能回复 ---
    
    # 1. 如果记忆中有报价，客户问数量/颜色，基于记忆回复
    if memory_section and ("套" in current_message or "数量" in current_message or "颜色" in msg_lower):
        # 从记忆中找上次报的型号和价格
        price_match = re.search(r'(T\d{3,4}).*?(\d+)元', memory_section)
        model_match = re.search(r'(T\d{3,4})', memory_section)
        
        if price_match:
            model = price_match.group(1)
            price = price_match.group(2)
            quantity = re.search(r'(\d+)', current_message)
            if quantity:
                return f"{model} {price}元一套，{quantity.group(1)}套可以优惠点。黑色白色灰色可选。"
            else:
                return f"{model} {price}元一套。要几套？颜色有黑白灰。"
    
    # 2. 如果记忆中有型号，客户继续问相关
    if memory_section and ("t412" in msg_lower or "t621" in msg_lower or "t423" in msg_lower):
        # 提取客户提到的型号
        model_mentioned = None
        for model in ["t412", "t621", "t423", "t524", "t728", "t523", "t724", "t727"]:
            if model in msg_lower:
                model_mentioned = model.upper()
                break
        
        if model_mentioned:
            # 如果问颜色/配置
            if any(kw in msg_lower for kw in ["颜色", "有什么色", "黑色", "白色"]):
                return f"{model_mentioned} 黑色白色灰色都有现货。要哪个颜色？"
            # 如果问价格
            if any(kw in msg_lower for kw in ["多少", "价格", "钱"]):
                prices = {"t412": "689", "t621": "835", "t423": "775", "t524": "415"}
                price = prices.get(model_mentioned.lower(), "")
                if price:
                    return f"{model_mentioned} {price}元一套出厂价。要几套？"
    
    # 3. 如果记忆中有合同相关，客户继续问
    if memory_section and "合同" in memory_section:
        if any(kw in msg_lower for kw in ["公司", "地址", "电话", "联系"]):
            return "好的，您把公司全称、收货地址、联系人电话发给我，我这就给您做合同。"
    
    # 4. 如果记忆中有预算询问，客户回复数字
    if memory_section and ("预算" in memory_section or "多少套" in memory_section):
        quantity_match = re.search(r'(\d+)\s*套', current_message)
        if quantity_match:
            qty = quantity_match.group(1)
            if int(qty) >= 100:
                return f"{qty}套是工程单，可以走工程价。具体型号确定了吗？"
            elif int(qty) >= 10:
                return f"{qty}套可以有优惠。要什么型号？"
    
    # --- 基础规则回复（无记忆时） ---
    
    if any(kw in msg_lower for kw in ["价格", "多少钱", "报价"]):
        return "T412双电机方管740元，T621椭圆管900元。需要几套？"
    
    if any(kw in msg_lower for kw in ["型号", "推荐", "哪款"]):
        return "预算什么范围？数量多少？我给您推荐合适的。"
    
    if "合同" in msg_lower:
        return "好的，请提供公司全称、联系人、电话、地址，我给您生成合同。"
    
    if any(kw in msg_lower for kw in ["谢谢", "感谢"]):
        return "不客气！有问题随时找我。"
    
    if any(kw in msg_lower for kw in ["在吗", "在？", "在?", "hello", "hi"]):
        return "在的，有什么可以帮您？"
    
    # 默认：基于记忆给通用回复
    if memory_section:
        # 看记忆最后一条是什么
        lines = [l.strip() for l in memory_section.split('\n') if l.strip()]
        if lines:
            last_line = lines[-1]
            if "李生:" in last_line:
                return "您看还有什么问题？或者说说具体需求。"
            elif "客户:" in last_line:
                return "收到，还有其他需要了解的吗？"
    
    return "收到，请问您想了解哪款升降桌？"


def generate_with_moonshot(prompt: str, contact: str = "") -> str:
    """
    使用 Moonshot API 生成回复（可选）
    """
    if not MOONSHOT_API_KEY:
        return ""
    
    try:
        import requests
        
        headers = {
            "Authorization": f"Bearer {MOONSHOT_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "moonshot-v1-8k",
            "messages": [
                {"role": "system", "content": "你是畅腾升降桌的客服李生，回复要简洁务实（50字以内），广东生意人风格。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        
        response = requests.post(MOONSHOT_API_URL, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            reply = result['choices'][0]['message']['content'].strip()
            log(f"[Moonshot] 生成回复: {reply[:50]}...")
            return reply
    except Exception as e:
        log(f"[Moonshot] API调用失败: {e}")
    
    return ""


if __name__ == "__main__":
    # 测试 - 基于记忆的回复
    test_cases = [
        {
            "name": "记住型号后问数量",
            "prompt": """历史相关记忆：
- 客户: T412多少钱？
- 李生: T412双电机方管689元，需要几套？

客户当前消息：要10套黑色的

请生成回复："""
        },
        {
            "name": "记住预算后问型号", 
            "prompt": """历史相关记忆：
- 客户: 200套什么价？
- 李生: 200套是工程单，可以走工程价

客户当前消息：T621有货吗？

请生成回复："""
        }
    ]
    
    for test in test_cases:
        print(f"\n=== {test['name']} ===")
        reply = generate_llm_reply(test['prompt'], "测试客户")
        print(f"回复: {reply}")
