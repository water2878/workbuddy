#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地客户画像推送工具 - 命令行版本

用法:
    python push_profiles.py [命令] [参数]

命令:
    push-all          推送所有本地客户画像到云端审批系统
    push-one <ID>     推送指定客户ID的画像到云端
    list              列出所有本地客户画像
    check             检查本地客户画像数据完整性
    help              显示帮助信息

示例:
    python push_profiles.py push-all           # 推送所有客户画像
    python push_profiles.py push-all --force   # 推送所有（包括不完整数据）
    python push_profiles.py push-one wxid_xxx  # 推送指定客户
    python push_profiles.py list               # 列出所有客户
    python push_profiles.py check              # 检查数据完整性
"""

import os
import sys
import argparse
from datetime import datetime

# 添加核心模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.customer_sync import (
    push_all_profiles_to_cloud,
    push_profile_by_customer_id,
    load_local_customer_profiles,
    is_profile_complete,
    get_profile_completeness,
    CLOUD_APPROVAL_SERVER
)


def print_banner():
    """打印工具横幅"""
    banner = """
╔══════════════════════════════════════════════════════════╗
║           本地客户画像推送工具 - 命令行版本                ║
║                      v1.0.0                             ║
║                                                          ║
║   目标服务器: {}  ║
╚══════════════════════════════════════════════════════════╝
    """.format(CLOUD_APPROVAL_SERVER)
    print(banner)


def cmd_push_all(args):
    """推送所有本地客户画像"""
    print(f"\n📤 开始推送所有本地客户画像到云端审批系统...")
    print(f"📍 目标服务器: {CLOUD_APPROVAL_SERVER}")
    print(f"🔍 过滤选项: {'仅推送完整数据' if not args.force else '推送所有数据'}")
    print("-" * 60)
    
    result = push_all_profiles_to_cloud(
        cloud_server=CLOUD_APPROVAL_SERVER,
        filter_complete=not args.force
    )
    
    print("\n📊 推送结果:")
    print(f"  总计待推送: {result.get('total', 0)}")
    print(f"  ✅ 成功: {result.get('success_count', 0)}")
    print(f"  ❌ 失败: {result.get('failed_count', 0)}")
    print(f"  ⚠️  数据不完整跳过: {result.get('skipped_incomplete', 0)}")
    
    if result.get("success_list"):
        print("\n✅ 成功推送列表:")
        for item in result["success_list"]:
            cloud_id = item.get("cloud_id", "")
            print(f"   - {item['name']} {f'(云端ID: {cloud_id})' if cloud_id else ''}")
    
    if result.get("failed_list"):
        print("\n❌ 推送失败列表:")
        for item in result["failed_list"]:
            print(f"   - {item['name']}: {item.get('error', '未知错误')}")
    
    print(f"\n📝 {result.get('message', '操作完成')}")


def cmd_push_one(args):
    """推送指定客户ID的画像"""
    if not args.customer_id:
        print("❌ 请指定客户ID，使用: push-one <customer_id>")
        return
    
    print(f"\n📤 推送指定客户画像...")
    print(f"📍 目标服务器: {CLOUD_APPROVAL_SERVER}")
    print(f"👤 客户ID: {args.customer_id}")
    print("-" * 60)
    
    result = push_profile_by_customer_id(
        customer_id=args.customer_id,
        cloud_server=CLOUD_APPROVAL_SERVER
    )
    
    if result["success"]:
        print(f"\n✅ 推送成功!")
        print(f"   客户名称: {result['customer_name']}")
        if result.get("cloud_id"):
            print(f"   云端ID: {result['cloud_id']}")
    else:
        print(f"\n❌ 推送失败!")
        print(f"   错误信息: {result.get('error', '未知错误')}")


def cmd_list(args):
    """列出所有本地客户画像"""
    profiles = load_local_customer_profiles()
    
    print(f"\n📋 本地客户画像列表 ({len(profiles)} 个)")
    print("-" * 80)
    
    if not profiles:
        print("   暂无客户画像数据")
        return
    
    for i, profile in enumerate(profiles, 1):
        customer_id = profile.get("customer_id", "N/A")
        nickname = profile.get("nickname", "未知昵称")
        first_contact = profile.get("first_contact", "N/A")
        priority = profile.get("priority", "N/A")
        is_complete = "✅" if is_profile_complete(profile) else "❌"
        
        print(f"{i:2d}. {is_complete} {nickname}")
        print(f"     ├── ID: {customer_id}")
        print(f"     ├── 首次联系: {first_contact}")
        print(f"     └── 优先级: {priority}")


def cmd_check(args):
    """检查本地客户画像数据完整性"""
    profiles = load_local_customer_profiles()
    
    print(f"\n🔍 检查本地客户画像数据完整性 ({len(profiles)} 个)")
    print("-" * 80)
    
    if not profiles:
        print("   暂无客户画像数据")
        return
    
    complete_count = 0
    incomplete_count = 0
    
    for profile in profiles:
        nickname = profile.get("nickname", "未知昵称")
        customer_id = profile.get("customer_id", "N/A")
        completeness = get_profile_completeness(profile)
        is_complete_flag = is_profile_complete(profile)
        
        if is_complete_flag:
            complete_count += 1
            status = "✅ 完整"
        else:
            incomplete_count += 1
            status = "❌ 不完整"
            missing = [k.replace("has_", "") for k, v in completeness.items() if not v]
            status += f" (缺少: {', '.join(missing)})"
        
        print(f"• {nickname} [{customer_id}]: {status}")
    
    print("-" * 80)
    print(f"📊 统计: 完整 {complete_count} 个, 不完整 {incomplete_count} 个")
    print(f"💡 建议: 使用 'push-all' 推送完整数据，或使用 'push-all --force' 强制推送所有")


def cmd_help(args):
    """显示帮助信息"""
    print(__doc__)


def main():
    parser = argparse.ArgumentParser(
        prog="push_profiles.py",
        description="本地客户画像推送工具 - 将本地客户画像数据推送到云端审批系统",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # push-all 命令
    push_all_parser = subparsers.add_parser(
        "push-all", 
        help="推送所有本地客户画像到云端审批系统",
        description="推送所有本地客户画像到云端审批系统"
    )
    push_all_parser.add_argument(
        "--force", 
        action="store_true", 
        help="强制推送所有数据，包括不完整的客户画像"
    )
    push_all_parser.set_defaults(func=cmd_push_all)
    
    # push-one 命令
    push_one_parser = subparsers.add_parser(
        "push-one", 
        help="推送指定客户ID的画像到云端",
        description="推送指定客户ID的画像到云端审批系统"
    )
    push_one_parser.add_argument(
        "customer_id", 
        nargs="?", 
        help="客户微信ID"
    )
    push_one_parser.set_defaults(func=cmd_push_one)
    
    # list 命令
    list_parser = subparsers.add_parser(
        "list", 
        help="列出所有本地客户画像",
        description="列出所有本地存储的客户画像"
    )
    list_parser.set_defaults(func=cmd_list)
    
    # check 命令
    check_parser = subparsers.add_parser(
        "check", 
        help="检查本地客户画像数据完整性",
        description="检查本地客户画像数据完整性，识别缺少必要字段的客户"
    )
    check_parser.set_defaults(func=cmd_check)
    
    # help 命令
    help_parser = subparsers.add_parser(
        "help", 
        help="显示帮助信息",
        description="显示详细的帮助信息"
    )
    help_parser.set_defaults(func=cmd_help)
    
    args = parser.parse_args()
    
    if not args.command:
        print_banner()
        parser.print_help()
        sys.exit(0)
    
    # 执行命令
    print_banner()
    args.func(args)


if __name__ == "__main__":
    main()
