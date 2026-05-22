"""
客户复盘系统
定时对高意向用户和已下单用户进行复盘分析
"""
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from core.weflow_client import WeFlowClient
from core.customer_profile import load_profile, save_profile, list_all_profiles, get_profile_path
from core.config import log, BASE_DIR


@dataclass
class ReviewResult:
    """复盘结果"""
    nickname: str
    customer_id: str
    review_date: str
    last_contact: str
    days_since_contact: int
    priority: str
    tags: List[str]
    
    # 分析结果
    has_order_history: bool
    order_count: int
    last_order_date: Optional[str]
    
    # 意向分析
    intention_level: str  # 高/中/低
    intention_reason: str
    
    # 复盘建议
    suggested_action: str
    suggested_message: str
    
    # 最新聊天摘要
    recent_chat_summary: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


class CustomerReviewSystem:
    """客户复盘系统"""
    
    def __init__(self, weflow_client: Optional[WeFlowClient] = None):
        self.weflow = weflow_client or self._create_weflow_client()
        self.review_results: List[ReviewResult] = []
        
    def _create_weflow_client(self) -> WeFlowClient:
        """创建WEFLOW客户端"""
        config_path = os.path.join(BASE_DIR, "config.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        weflow_config = config.get("weflow", {})
        return WeFlowClient(
            base_url=weflow_config.get("base_url", "http://127.0.0.1:5031"),
            token=weflow_config.get("access_token", "")
        )
    
    def get_high_priority_customers(self) -> List[Dict]:
        """获取高优先级客户（高意向或已下单）"""
        all_profiles = list_all_profiles()
        high_priority = []
        
        for profile_summary in all_profiles:
            nickname = profile_summary["nickname"]
            profile = load_profile(nickname)
            
            if not profile:
                continue
            
            # 判断是否为高优先级客户
            is_high_priority = self._is_high_priority_customer(profile)
            
            if is_high_priority:
                profile_summary["full_profile"] = profile
                high_priority.append(profile_summary)
        
        # 按优先级排序（高 -> 中 -> 低）
        priority_order = {"高": 0, "中": 1, "低": 2}
        high_priority.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return high_priority
    
    def _is_high_priority_customer(self, profile: Dict) -> bool:
        """判断是否为高优先级客户"""
        # 1. 优先级标记为高
        if profile.get("priority") == "高":
            return True
        
        # 2. 有订单历史
        orders = profile.get("orders", [])
        if orders and len(orders) > 0:
            return True
        
        # 3. 标签包含高意向相关
        high_intention_tags = ["高意向", "已下单", "重点跟进", "批发客户", "定制需求"]
        tags = profile.get("tags", [])
        if any(tag in high_intention_tags for tag in tags):
            return True
        
        # 4. 交互记录中有高意向标记
        interactions = profile.get("interactions", [])
        for interaction in interactions:
            if interaction.get("intention") in ["高", "中"]:
                return True
        
        # 5. 需求类型为批发或定制
        demand_type = profile.get("profile", {}).get("demand_type", {}).get("value", "")
        if demand_type in ["批发", "定制", "项目"]:
            return True
        
        return False
    
    def fetch_weflow_chat_history(self, session_id: str, days: int = 7) -> List[Dict]:
        """从WEFLOW获取指定会话的聊天历史"""
        try:
            # 计算时间范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 格式化时间（YYYYMMDD）
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            
            # 获取消息
            response = self.weflow.get_messages(
                talker=session_id,
                limit=100,
                start=start_str,
                end=end_str
            )
            
            messages = response.get("messages", [])
            log(f"[复盘系统] 获取到 {len(messages)} 条消息: {session_id[:20]}...")
            return messages
            
        except Exception as e:
            log(f"[复盘系统] 获取聊天历史失败 {session_id}: {e}", "ERROR")
            return []
    
    def analyze_chat_intention(self, messages: List[Dict], profile: Dict) -> Dict:
        """分析聊天内容的意向"""
        if not messages:
            return {
                "intention_level": "未知",
                "reason": "近期无聊天记录",
                "has_purchase_intent": False
            }
        
        # 提取客户发送的消息
        customer_messages = []
        for msg in messages:
            content = msg.get("content", "")
            sender = msg.get("senderUsername", "")
            
            # 排除自己发送的消息（假设assistant的消息包含特定标记或从profile判断）
            if content and len(content) > 5:
                customer_messages.append(content)
        
        if not customer_messages:
            return {
                "intention_level": "未知",
                "reason": "无有效客户消息",
                "has_purchase_intent": False
            }
        
        # 分析关键词
        all_text = " ".join(customer_messages).lower()
        
        # 高意向关键词
        high_intent_keywords = [
            "报价", "多少钱", "价格", "下单", "订购", "采购", "买", "要", "确定",
            "合同", "付款", "发货", "急", "尽快", "现在", "今天", "明天"
        ]
        
        # 中意向关键词
        medium_intent_keywords = [
            "考虑", "看看", "了解一下", "对比", "合适", "怎么样", "能否", "可以",
            "推荐", "有什么", "型号", "规格", "参数"
        ]
        
        # 低意向关键词
        low_intent_keywords = [
            "不用", "不需要", "太贵", "再看看", "以后", "算了", "拜拜", "谢谢"
        ]
        
        high_count = sum(1 for kw in high_intent_keywords if kw in all_text)
        medium_count = sum(1 for kw in medium_intent_keywords if kw in all_text)
        low_count = sum(1 for kw in low_intent_keywords if kw in all_text)
        
        # 判断意向等级
        if high_count > 0 and low_count == 0:
            intention_level = "高"
            reason = f"检测到{high_count}个高意向关键词"
            has_purchase_intent = True
        elif medium_count > 0 or (high_count > 0 and low_count > 0):
            intention_level = "中"
            reason = f"检测到{medium_count}个中意向关键词"
            has_purchase_intent = True
        elif low_count > 0:
            intention_level = "低"
            reason = f"检测到{low_count}个低意向关键词"
            has_purchase_intent = False
        else:
            intention_level = "中"
            reason = "有互动但未明确意向"
            has_purchase_intent = True
        
        return {
            "intention_level": intention_level,
            "reason": reason,
            "has_purchase_intent": has_purchase_intent,
            "keywords_found": {
                "high": high_count,
                "medium": medium_count,
                "low": low_count
            }
        }
    
    def generate_suggested_action(self, profile: Dict, intention_analysis: Dict, 
                                   days_since_contact: int) -> Dict:
        """生成复盘建议"""
        orders = profile.get("orders", [])
        has_order = len(orders) > 0
        intention = intention_analysis.get("intention_level", "未知")
        
        # 根据情况生成建议
        if has_order:
            # 已下单客户
            last_order = orders[-1]
            order_date = last_order.get("date", "")
            
            if days_since_contact > 14:
                suggested_action = "回访老客户"
                suggested_message = f"{profile.get('nickname', '客户')}您好，之前订购的产品使用还满意吗？有没有新的采购需求？"
            else:
                suggested_action = "保持联系"
                suggested_message = f"{profile.get('nickname', '客户')}您好，跟进一下之前的订单进度，有任何问题随时联系。"
        
        elif intention == "高":
            if days_since_contact > 3:
                suggested_action = "紧急跟进"
                suggested_message = f"{profile.get('nickname', '客户')}您好，之前您咨询的产品考虑得怎么样？有什么疑问我可以帮您解答。"
            else:
                suggested_action = "持续跟进"
                suggested_message = f"{profile.get('nickname', '客户')}您好，关于您感兴趣的产品，我给您准备了更详细的资料。"
        
        elif intention == "中":
            if days_since_contact > 7:
                suggested_action = "温和跟进"
                suggested_message = f"{profile.get('nickname', '客户')}您好，最近有新的产品优惠，不知道您还有需求吗？"
            else:
                suggested_action = "提供价值"
                suggested_message = f"{profile.get('nickname', '客户')}您好，分享一些行业资讯和产品应用场景，供您参考。"
        
        else:  # 低意向或未知
            if days_since_contact > 30:
                suggested_action = "激活客户"
                suggested_message = f"{profile.get('nickname', '客户')}您好，很久没联系了，我们推出了新款升降桌，想给您介绍一下。"
            else:
                suggested_action = "保持曝光"
                suggested_message = f"{profile.get('nickname', '客户')}您好，朋友圈有新动态，欢迎了解我们的产品。"
        
        return {
            "action": suggested_action,
            "message": suggested_message
        }
    
    def review_customer(self, nickname: str, profile: Dict, 
                        session_id: Optional[str] = None) -> Optional[ReviewResult]:
        """对单个客户进行复盘"""
        try:
            # 获取客户ID
            customer_id = profile.get("customer_id", "")
            
            # 如果没有session_id，尝试从customer_id构造
            if not session_id and customer_id:
                session_id = customer_id
            
            # 计算最后联系时间
            last_contact_str = profile.get("last_contact", "")
            if last_contact_str:
                try:
                    last_contact = datetime.strptime(last_contact_str, "%Y-%m-%d")
                    days_since_contact = (datetime.now() - last_contact).days
                except:
                    days_since_contact = 999
            else:
                days_since_contact = 999
            
            # 获取订单历史
            orders = profile.get("orders", [])
            has_order_history = len(orders) > 0
            last_order_date = orders[-1].get("date") if orders else None
            
            # 获取最新聊天历史
            messages = []
            if session_id:
                messages = self.fetch_weflow_chat_history(session_id, days=7)
            
            # 分析意向
            intention_analysis = self.analyze_chat_intention(messages, profile)
            
            # 生成建议
            suggestion = self.generate_suggested_action(
                profile, intention_analysis, days_since_contact
            )
            
            # 生成聊天摘要
            if messages:
                recent_msgs = messages[-5:]  # 最近5条
                chat_summary = " | ".join([
                    msg.get("content", "")[:30] 
                    for msg in recent_msgs 
                    if msg.get("content")
                ])
            else:
                chat_summary = "近期无聊天记录"
            
            # 创建复盘结果
            result = ReviewResult(
                nickname=nickname,
                customer_id=customer_id,
                review_date=datetime.now().strftime("%Y-%m-%d"),
                last_contact=last_contact_str,
                days_since_contact=days_since_contact,
                priority=profile.get("priority", "中"),
                tags=profile.get("tags", []),
                has_order_history=has_order_history,
                order_count=len(orders),
                last_order_date=last_order_date,
                intention_level=intention_analysis["intention_level"],
                intention_reason=intention_analysis["reason"],
                suggested_action=suggestion["action"],
                suggested_message=suggestion["message"],
                recent_chat_summary=chat_summary[:100]  # 限制长度
            )
            
            return result
            
        except Exception as e:
            log(f"[复盘系统] 复盘客户失败 {nickname}: {e}", "ERROR")
            return None
    
    def run_review(self, days_threshold: int = 30) -> List[ReviewResult]:
        """
        执行复盘任务
        
        Args:
            days_threshold: 只复盘超过N天未联系的客户（0表示全部）
        """
        log("[复盘系统] 开始执行客户复盘...")
        
        # 获取高优先级客户
        high_priority_customers = self.get_high_priority_customers()
        log(f"[复盘系统] 找到 {len(high_priority_customers)} 个高优先级客户")
        
        results = []
        
        for customer_summary in high_priority_customers:
            nickname = customer_summary["nickname"]
            profile = customer_summary.get("full_profile", {})
            
            # 检查最后联系时间
            last_contact = profile.get("last_contact", "")
            if last_contact and days_threshold > 0:
                try:
                    last_date = datetime.strptime(last_contact, "%Y-%m-%d")
                    days_passed = (datetime.now() - last_date).days
                    if days_passed < days_threshold:
                        continue  # 跳过近期联系过的客户
                except:
                    pass
            
            # 执行复盘
            result = self.review_customer(nickname, profile)
            if result:
                results.append(result)
                log(f"[复盘系统] 复盘完成: {nickname} - 意向{result.intention_level}")
        
        self.review_results = results
        log(f"[复盘系统] 复盘完成，共 {len(results)} 个客户")
        
        return results
    
    def export_review_report(self, output_path: Optional[str] = None) -> str:
        """导出复盘报告"""
        if not self.review_results:
            return "暂无复盘结果"
        
        if not output_path:
            output_path = os.path.join(
                BASE_DIR, "data", 
                f"review_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
        
        # 按意向等级分组
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_customers": len(self.review_results),
            "summary": {
                "high_intention": len([r for r in self.review_results if r.intention_level == "高"]),
                "medium_intention": len([r for r in self.review_results if r.intention_level == "中"]),
                "low_intention": len([r for r in self.review_results if r.intention_level == "低"]),
                "with_orders": len([r for r in self.review_results if r.has_order_history]),
            },
            "customers": [r.to_dict() for r in self.review_results]
        }
        
        # 保存报告
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        log(f"[复盘系统] 复盘报告已保存: {output_path}")
        return output_path
    
    def generate_action_list(self) -> str:
        """生成行动清单（文本格式）"""
        if not self.review_results:
            return "暂无复盘结果"
        
        lines = [
            "=" * 60,
            "客户复盘行动清单",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            ""
        ]
        
        # 按建议行动分组
        action_groups = {}
        for result in self.review_results:
            action = result.suggested_action
            if action not in action_groups:
                action_groups[action] = []
            action_groups[action].append(result)
        
        # 生成清单
        for action, customers in sorted(action_groups.items()):
            lines.append(f"\n【{action}】({len(customers)}人)")
            lines.append("-" * 40)
            
            for c in customers:
                lines.append(f"\n  客户: {c.nickname}")
                lines.append(f"  意向: {c.intention_level} ({c.intention_reason})")
                lines.append(f"  未联系: {c.days_since_contact}天")
                if c.has_order_history:
                    lines.append(f"  订单: {c.order_count}笔")
                lines.append(f"  建议话术: {c.suggested_message}")
                lines.append("")
        
        return "\n".join(lines)


# 便捷函数
def run_customer_review(days_threshold: int = 0) -> List[ReviewResult]:
    """执行客户复盘（便捷函数）"""
    reviewer = CustomerReviewSystem()
    return reviewer.run_review(days_threshold=days_threshold)


def generate_daily_review() -> str:
    """生成每日复盘报告"""
    reviewer = CustomerReviewSystem()
    
    # 复盘所有高优先级客户
    reviewer.run_review(days_threshold=0)
    
    # 导出报告
    report_path = reviewer.export_review_report()
    
    # 生成行动清单
    action_list = reviewer.generate_action_list()
    
    return action_list


if __name__ == "__main__":
    # 测试运行
    print("=" * 60)
    print("客户复盘系统测试")
    print("=" * 60)
    
    # 执行复盘
    action_list = generate_daily_review()
    print(action_list)
