#!/usr/bin/env python3
"""生成健康办公研究社合同"""
import requests
import json

url = "http://127.0.0.1:5032/api/contracts/generate"

payload = {
    "customer_name": "健康办公研究社",
    "customer_contact": "李飞",
    "customer_phone": "15088006879",
    "customer_address": "",
    "products": [
        {
            "model": "T423",
            "quantity": 100,
            "unit_price": 775,
            "subtotal": 77500,
            "frame_color": "黑色"
        },
        {
            "model": "E0",
            "quantity": 100,
            "unit_price": 218,
            "subtotal": 21800,
            "frame_color": "黑色",
            "frame_size": "1400*700*25mm"
        }
    ],
    "customer_nickname": "健康办公研究社",
    "delivery_date": "一个月之内",
    "payment_terms": "",
    "notes": "面板：1400*700 25mm 黑色"
}

response = requests.post(url, json=payload)
print(json.dumps(response.json(), ensure_ascii=False, indent=2))
