#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快捷发送消息给客户（自动更新客户画像）
用法: 
  python send_reply.py "客户名称" "消息内容"              # 发文字
  python send_reply.py "客户名称" "IMAGE:图片路径"       # 发指定图片
  python send_reply.py "客户名称" "MODEL:T524"           # 智能发产品图（最佳角度）
  python send_reply.py "客户名称" "MODEL:T524:next"      # 顺序发下一张
  python send_reply.py "客户名称" "MODEL:T524:index:0"   # 发指定序号
"""
import sys
import os
from datetime import datetime
sys.path.insert(0, 'sender')
sys.path.insert(0, 'core')
from wechat_sender import send_text_safe, send_image_safe
from customer_profile import add_interaction, update_profile_field
from product_service import get_next_image_for_customer

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python send_reply.py \"客户名称\" \"消息内容\"")
        print("      python send_reply.py \"客户名称\" \"IMAGE:图片路径\"")
        print("      python send_reply.py \"客户名称\" \"MODEL:型号\"")
        print("      python send_reply.py \"客户名称\" \"MODEL:型号:next\"")
        print("示例: python send_reply.py \"健康办公研究社\" \"您好！\"")
        print("      python send_reply.py \"健康办公研究社\" \"MODEL:T524\"")
        sys.exit(1)
    
    contact = sys.argv[1]
    message = sys.argv[2]
    
    # 判断消息类型
    if message.startswith("IMAGE:"):
        # 发指定图片
        image_path = message[6:]  # 去掉 "IMAGE:" 前缀
        if not os.path.exists(image_path):
            print(f"❌ 图片不存在: {image_path}")
            sys.exit(1)
        print(f"发送图片给 {contact}...")
        result = send_image_safe(contact, image_path)
        content = f"[图片] {os.path.basename(image_path)}"
        
    elif message.startswith("MODEL:"):
        # 智能发产品图
        parts = message.split(":")
        model = parts[1] if len(parts) > 1 else ""
        request_type = "smart"
        if len(parts) > 2:
            if parts[2] == "next":
                request_type = "next"
            elif parts[2] == "index" and len(parts) > 3:
                request_type = f"index:{parts[3]}"
        
        print(f"智能选图: {model} ({request_type})...")
        image_path, desc = get_next_image_for_customer(
            model=model, 
            customer_id=contact,
            request_type=request_type
        )
        
        if not image_path:
            print(f"❌ 未找到 {model} 的图片")
            # 通知资料员补充资料
            try:
                from config import MATERIALS_CONTACT, API_HOST, API_PORT
                if MATERIALS_CONTACT:
                    materials_url = f"http://{API_HOST}:{API_PORT}/materials"
                    notify_msg = f"""📢 资料补充提醒

产品型号：{model}
缺少内容：客户[{contact}]请求产品图片，但该型号缺少图片资料
请求时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

👉 点击链接补充资料：
{materials_url}

请尽快上传产品图片，谢谢！"""
                    send_text_safe(MATERIALS_CONTACT, notify_msg)
                    print(f"📢 已通知资料员补充 {model} 的图片")
            except Exception as e:
                print(f"⚠️ 通知资料员失败: {e}")
            sys.exit(1)
        
        print(f"选中: {os.path.basename(image_path)}")
        result = send_image_safe(contact, image_path)
        content = f"[图片] {desc}"
        
    else:
        # 发文字
        print(f"发送消息给 {contact}...")
        result = send_text_safe(contact, message)
        content = message[:100] + "..." if len(message) > 100 else message
    
    if result["success"]:
        print(f"✅ 发送成功")
        # 自动更新客户画像
        try:
            add_interaction(
                nickname=contact,
                interaction_type="客服回复",
                content=content,
                intention="已回复客户",
                next_action="等待客户回复"
            )
            print(f"📝 客户画像已更新")
        except Exception as e:
            print(f"⚠️ 画像更新失败: {e}")
    else:
        print(f"❌ 发送失败: {result.get('error', '未知错误')}")
