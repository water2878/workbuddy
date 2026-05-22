"""
客户复盘定时调度器
支持定时执行客户复盘任务
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.customer_review import CustomerReviewSystem, generate_daily_review
from core.config import log, BASE_DIR


class ReviewScheduler:
    """复盘任务调度器"""
    
    def __init__(self):
        self.reviewer = CustomerReviewSystem()
        self.running = False
        self.schedule_config = self._load_schedule_config()
    
    def _load_schedule_config(self) -> dict:
        """加载调度配置"""
        config_path = os.path.join(BASE_DIR, "data", "review_schedule.json")
        default_config = {
            "enabled": True,
            "daily_time": "09:00",  # 每天执行时间
            "days_threshold": 3,    # 复盘超过3天未联系的客户
            "output_dir": os.path.join(BASE_DIR, "data", "review_reports"),
            "last_run": None,
            "notification": {
                "enabled": True,
                "method": "console"  # console/file/wechat
            }
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    default_config.update(config)
            except Exception as e:
                log(f"[调度器] 加载配置失败: {e}", "ERROR")
        
        # 确保输出目录存在
        os.makedirs(default_config["output_dir"], exist_ok=True)
        
        return default_config
    
    def _save_schedule_config(self):
        """保存调度配置"""
        config_path = os.path.join(BASE_DIR, "data", "review_schedule.json")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.schedule_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f"[调度器] 保存配置失败: {e}", "ERROR")
    
    def run_once(self, days_threshold: Optional[int] = None) -> str:
        """
        执行一次复盘任务
        
        Returns:
            行动清单文本
        """
        threshold = days_threshold if days_threshold is not None else self.schedule_config.get("days_threshold", 0)
        
        log(f"[调度器] 开始执行复盘任务 (阈值: {threshold}天)...")
        
        # 执行复盘
        results = self.reviewer.run_review(days_threshold=threshold)
        
        if not results:
            log("[调度器] 没有需要复盘的客户")
            return "没有需要复盘的客户"
        
        # 导出报告
        report_filename = f"review_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = os.path.join(self.schedule_config["output_dir"], report_filename)
        self.reviewer.export_review_report(report_path)
        
        # 生成行动清单
        action_list = self.reviewer.generate_action_list()
        
        # 保存行动清单
        list_filename = f"action_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        list_path = os.path.join(self.schedule_config["output_dir"], list_filename)
        with open(list_path, 'w', encoding='utf-8') as f:
            f.write(action_list)
        
        # 更新最后执行时间
        self.schedule_config["last_run"] = datetime.now().isoformat()
        self._save_schedule_config()
        
        log(f"[调度器] 复盘完成: {len(results)} 个客户")
        log(f"[调度器] 报告保存: {report_path}")
        log(f"[调度器] 行动清单: {list_path}")
        
        return action_list
    
    def run_daily(self):
        """每日定时执行"""
        log("[调度器] 启动每日定时复盘调度器...")
        log(f"[调度器] 执行时间: {self.schedule_config['daily_time']}")
        log(f"[调度器] 复盘阈值: {self.schedule_config['days_threshold']}天")
        
        self.running = True
        
        while self.running:
            try:
                now = datetime.now()
                target_time = datetime.strptime(self.schedule_config["daily_time"], "%H:%M").time()
                target_datetime = datetime.combine(now.date(), target_time)
                
                # 如果今天的时间已过，设置为明天
                if now > target_datetime:
                    target_datetime += timedelta(days=1)
                
                # 计算等待时间
                wait_seconds = (target_datetime - now).total_seconds()
                
                log(f"[调度器] 下次执行时间: {target_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
                log(f"[调度器] 等待 {int(wait_seconds)} 秒...")
                
                # 等待到执行时间
                while wait_seconds > 0 and self.running:
                    sleep_time = min(60, wait_seconds)  # 每分钟检查一次
                    time.sleep(sleep_time)
                    wait_seconds -= sleep_time
                
                if not self.running:
                    break
                
                # 执行复盘
                log("[调度器] 到达执行时间，开始复盘...")
                self.run_once()
                
                # 等待一段时间避免重复执行
                time.sleep(60)
                
            except Exception as e:
                log(f"[调度器] 执行出错: {e}", "ERROR")
                time.sleep(300)  # 出错后等待5分钟
        
        log("[调度器] 调度器已停止")
    
    def stop(self):
        """停止调度器"""
        self.running = False
        log("[调度器] 正在停止...")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="客户复盘调度器")
    parser.add_argument(
        "--once", 
        action="store_true", 
        help="立即执行一次复盘"
    )
    parser.add_argument(
        "--daily", 
        action="store_true", 
        help="启动每日定时调度"
    )
    parser.add_argument(
        "--threshold", 
        type=int, 
        default=None,
        help="复盘阈值天数（默认使用配置）"
    )
    parser.add_argument(
        "--time", 
        type=str, 
        default=None,
        help="设置每日执行时间 (HH:MM)"
    )
    
    args = parser.parse_args()
    
    scheduler = ReviewScheduler()
    
    # 设置执行时间
    if args.time:
        scheduler.schedule_config["daily_time"] = args.time
        scheduler._save_schedule_config()
        print(f"已设置每日执行时间为: {args.time}")
        return
    
    # 立即执行一次
    if args.once:
        print("=" * 60)
        print("执行客户复盘")
        print("=" * 60)
        action_list = scheduler.run_once(days_threshold=args.threshold)
        print(action_list)
        return
    
    # 启动定时调度
    if args.daily:
        try:
            scheduler.run_daily()
        except KeyboardInterrupt:
            print("\n用户中断，正在停止...")
            scheduler.stop()
        return
    
    # 默认：立即执行一次
    print("=" * 60)
    print("执行客户复盘 (使用 --help 查看所有选项)")
    print("=" * 60)
    action_list = scheduler.run_once(days_threshold=args.threshold)
    print(action_list)


if __name__ == "__main__":
    main()
