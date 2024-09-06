import os
import time
import requests
import json
import urllib.parse
import re
import schedule
import random
from pathlib import Path
from nonebot import on_command, require, get_bot
from nonebot.adapters.onebot.v11 import Bot, Event,MessageEvent, MessageSegment, GroupMessageEvent, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.typing import T_State
from nonebot_plugin_apscheduler import scheduler
import smtplib
from email.mime.text import MIMEText
from email.header import Header



# 定义存储路径
BINDINGS_DIR = "bindings"
REMINDERS_FILE = "reminder_list.json"

# 检查提醒列表文件是否存在，如果不存在则创建一个空文件
if not os.path.exists(REMINDERS_FILE):
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=4)

# 确保存储绑定信息的目录存在
if not os.path.exists(BINDINGS_DIR):
    os.makedirs(BINDINGS_DIR)

test_command = on_command("测试1234")
test2_command = on_command("测试12345")
electron_help = on_command("电费help")


@test_command.handle()
async def handle_test_command(bot: Bot, event: Event):
    # 发送回复消息
    await bot.send(event, "这是一个测试")

@electron_help.handle()
async def handle_test_command(bot: Bot, event: Event):
    await bot.send(event, "这是一个电费余量查询以及提醒功能，使用前需要绑定对应的账户，脚本来源详见：https://jsjxsgz.qd.sdu.edu.cn/info/1086/1471.htm ，bot插件的源码已上传至github(https://github.com/zzysssigm/sdu_electron_query/tree/master)，目前仅支持山东大学青岛校区 。\n具体而言，需要绑定你的宿舍楼,宿舍号,以及个人账户，其中[个人账户]是你的山大V卡通6位数字。 \n可以使用: \n/电费绑定 [宿舍楼] [宿舍号] [个人账户] 指令 \n/定时提醒 指令 \n/取消提醒 指令 \n/电费解绑 指令 \n以进行下一步操作。\n如：/电费绑定 B2 408 114514\n/电费绑定 B1 A543 191981 等\n更新日志：2024.9.6\n新增邮件发送电费定时提醒的功能；\n新增/内测功能 指令")

# 定义楼号与buildingid的映射关系
building_id_map = {
    "B1": "1661835249",
    "B2": "1661835256",
    "B9": "1693031698",
    "B10": "1693031710",
    "S1": "1503975832",
    "S2": "1503975890",
    "S5": "1503975967",
    "S6": "1503975980",
    "S7": "1503975988",
    "S8": "1503975995",
    "S9": "1503976004",
    "S10": "1503976037",
    "S11": "1599193777",
}

# 创建一个命令处理器
bind = on_command("电费绑定", aliases={"电费绑定"}, priority=5)

unbind = on_command("电费解绑", aliases={"电费解绑"}, priority=5)

@bind.handle()
async def handle_first_receive(bot: Bot, event: Event):
    # 获取参数
    args = str(event.get_message()).strip().split()

    # 获取用户QQ号及消息类型
    user_id = event.get_user_id()

    # 检查输入是否符合格式
    if len(args) != 4:
        if isinstance(event, GroupMessageEvent):
            message = MessageSegment.at(user_id) + " 输入格式错误！正确格式为：/电费绑定 [宿舍楼号] [宿舍号] [个人账户]，注意[宿舍楼号]需要大写字母，[个人账户]为山大V卡通的六位数字。"
            group_id = event.group_id
            await bot.call_api("send_group_msg", group_id=group_id, message=message)
            await query_elec.finish()
        else:
            await bind.finish(" 输入格式错误！正确格式为：/电费绑定 [宿舍楼号] [宿舍号] [个人账户]，注意[宿舍楼号]需要大写字母，[个人账户]为山大V卡通的六位数字。")

    # 获取用户输入的楼号、宿舍号
    building = args[1]
    room = args[2]
    account = args[3]
    
    # 检查楼号是否有效
    if building not in building_id_map:
        if isinstance(event, GroupMessageEvent):
            message = MessageSegment.at(user_id) + f" 无效的宿舍楼号！当前仅支持楼号：{', '.join(building_id_map.keys())}"
            group_id = event.group_id
            await bot.call_api("send_group_msg", group_id=group_id, message=message)
            await query_elec.finish()
        else:
            await bind.finish(f" 无效的宿舍楼号！当前仅支持楼号：{', '.join(building_id_map.keys())}")

    # 构建绑定信息的JSON内容
    bind_info = {
        "account": account, 
        "building": {
            "buildingid": building_id_map[building],
            "building": building
        },
        "room": room,
    }

    # 检查用户是否已经绑定过
    json_file_path = Path(f"bindings/{user_id}.json")
    if json_file_path.exists():
        if isinstance(event, GroupMessageEvent):
            message = MessageSegment.at(user_id) + " 您已经绑定过了，如需修改绑定信息，请先使用 /电费解绑 删除旧的绑定文件。"
            group_id = event.group_id
            await bot.call_api("send_group_msg", group_id=group_id, message=message)
            await query_elec.finish()
        else:
            await bind.finish(" 您已经绑定过了，如需修改绑定信息，请先使用 /电费解绑 删除旧的绑定文件。")

    # 如果没有绑定，则生成对应的JSON文件
    os.makedirs("bindings", exist_ok=True)  # 确保bindings目录存在
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(bind_info, f, ensure_ascii=False, indent=4)

    if isinstance(event, GroupMessageEvent):
        message = MessageSegment.at(user_id) + " 绑定成功！您的宿舍信息已保存。"
        group_id = event.group_id
        await bot.call_api("send_group_msg", group_id=group_id, message=message)
        await query_elec.finish()
    else:
        await bind.finish(" 绑定成功！您的宿舍信息已保存。")


@unbind.handle()
async def handle_unbind(bot: Bot, event: Event):
    # 获取用户QQ号及消息类型
    user_id = event.get_user_id()
    event_type = event.get_type()

    # 绑定信息的JSON文件路径
    json_file_path = Path(f"bindings/{user_id}.json")

    # 检查用户是否已经绑定过
    if not json_file_path.exists():
        if event_type == "group":
            message = MessageSegment.at(user_id) + " 您尚未绑定，无需解绑。"
            group_id = event.group_id
            await bot.call_api("send_group_msg", group_id=group_id, message=message)
            await query_elec.finish()
        else:
            await unbind.finish(" 您尚未绑定，无需解绑。")

    # 删除JSON文件以解除绑定
    json_file_path.unlink()
    if isinstance(event, GroupMessageEvent):
        message = MessageSegment.at(user_id) + " 解绑成功！您的宿舍信息已删除。"
        group_id = event.group_id
        await bot.call_api("send_group_msg", group_id=group_id, message=message)
        await query_elec.finish()
    else:
        await unbind.finish(" 解绑成功！您的宿舍信息已删除。")


# 创建一个电费查询命令处理器
query_elec = on_command("电费查询", aliases={"查询电费"}, priority=5)

@query_elec.handle()
async def handle_query_elec(bot: Bot, event: Event):
    # 获取用户QQ号及消息类型
    user_id = event.get_user_id()
    event_type = event.get_type()
    print(event_type)
    # if isinstance(event, GroupMessageEvent):
    #     print("Yes!BanGDream!")
    # 绑定信息的JSON文件路径
    json_file_path = Path(f"bindings/{user_id}.json")

    # 检查用户是否已经绑定过
    if not json_file_path.exists():
        if isinstance(event, GroupMessageEvent):
            message = MessageSegment.at(user_id) + " 您尚未绑定，请先使用 /电费绑定 命令绑定您的宿舍信息。"
            group_id = event.group_id
            await bot.call_api("send_group_msg", group_id=group_id, message=message)
            await query_elec.finish()
        else:
            await query_elec.finish(" 您尚未绑定，请先使用 /电费绑定 命令绑定您的宿舍信息。")

    # 读取绑定信息
    with json_file_path.open("r", encoding="utf-8") as file:
        binding_info = json.load(file)

    # 查询电量信息
    remaining_power = await query_electricity(binding_info)

    if remaining_power <= 8:
        message = MessageSegment.at(user_id) + f" 警告：电量余额为 {remaining_power} ，请尽快充值！"
        if isinstance(event, GroupMessageEvent):
            group_id = event.group_id  # 获取群号
            await bot.call_api("send_group_msg", group_id=group_id, message=message)
            await query_elec.finish()
        else:
            await query_elec.finish(f" 警告：剩余电量余额为 {remaining_power} ，请尽快充值！")
    else:
        message = MessageSegment.at(user_id) + f" 查询成功：当前剩余电量余额为 {remaining_power} 。"
        if isinstance(event, GroupMessageEvent):
            group_id = event.group_id  # 获取群号
            await bot.call_api("send_group_msg", group_id=group_id, message=message)
            await query_elec.finish()
        else:
            await query_elec.finish(f" 查询成功：当前剩余电量余额为 {remaining_power} 。")


async def query_electricity(binding_info):
    session = requests.session()  # 创建一个会话对象
    header = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G9600 Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/86.0.4240.198 Mobile Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    json_data = '''
    {
        "query_elec_roominfo": {
            "aid": "0030000000002505",
            "account": "000000",
            "room": {
                "roomid": "B999",
                "room": "B999"
            },
            "floor": {
                "floorid": "",
                "floor": ""
            },
            "area": {
                "area": "青岛校区",
                "areaname": "青岛校区"
            },
            "building": {
                "buildingid": "1503975890",
                "building": "S2从文书院"
            }
        }
    }
    '''
    js = json.loads(json_data)  # 将JSON字符串转换为Python对象

    # 更新请求数据
    js["query_elec_roominfo"]["account"] = binding_info["account"]
    js["query_elec_roominfo"]["room"]["roomid"] = binding_info["room"]
    js["query_elec_roominfo"]["room"]["room"] = binding_info["room"]
    js["query_elec_roominfo"]["building"] = binding_info["building"]

    js = json.dumps(js, ensure_ascii=False)  # 将Python对象转换为JSON字符串
    js = urllib.parse.quote(js)  # 对JSON字符串进行URL编码
    data = "jsondata=" + js + "&funname=synjones.onecard.query.elec.roominfo&json=true"

    # 发送POST请求
    res = session.post(url="http://10.100.1.24:8988/web/Common/Tsm.html", headers=header, data=data)
    response_json = json.loads(res.text)  # 解析响应内容

    # 使用正则表达式提取电量信息
    match = re.search(r"\d+\.\d+", response_json['query_elec_roominfo']['errmsg'])
    if match:
        remaining_power = float(match.group())
        return remaining_power
    else:
        return 0.0  # 如果没有找到电量信息，则返回0

    
set_reminder = on_command("定时提醒", priority=5)
remove_reminder = on_command("取消提醒", priority=5)

# 定时任务调度器
scheduler = require("nonebot_plugin_apscheduler").scheduler

@set_reminder.handle()
async def handle_set_reminder_command(bot: Bot, event: Event):
    user_id = event.get_user_id()
    json_file_path = Path(f"{BINDINGS_DIR}/{user_id}.json")

    if not json_file_path.exists():
        await bot.send(event, " 您尚未绑定，请先使用 /电费绑定 绑定您的宿舍信息。")
        return

    with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
        reminders = json.load(f)

    if user_id in reminders:
        await bot.send(event, " 您已设置过提醒，无需重复设置。")
        return

    reminders[user_id] = True

    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=False, indent=4)

    await bot.send(event, " 定时提醒设置成功！每日晚上9点将发送电费余额提醒。")

@remove_reminder.handle()
async def handle_remove_reminder_command(bot: Bot, event: Event):
    user_id = event.get_user_id()

    with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
        reminders = json.load(f)

    if user_id not in reminders:
        await bot.send(event, " 您尚未设置提醒，无需取消。")
        return

    del reminders[user_id]

    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=False, indent=4)

    await bot.send(event, " 定时提醒已取消。")


def send_email(to_email, subject, body):
    # 发件人信息(bot)
    sender_email = "2905326120@qq.com"
    sender_password = "hadywnsievawddjf"  # SMTP

    # SMTP 服务器
    smtp_server = "smtp.qq.com"
    smtp_port = 465

    # 邮件内容
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = Header(subject, 'utf-8')

    # 发送邮件
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [to_email], msg.as_string())
        print(f"邮件已发送到 {to_email}")
    except Exception as e:
        print(f"发送邮件时发生错误: {e}")



@scheduler.scheduled_job("cron", hour=21, minute=0)
async def scheduled_reminder():
    bot = get_bot()  # 获取 Bot 实例
    with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
        reminders = json.load(f)

    # 获取所有好友的 user_id 列表
    friend_list = await bot.get_friend_list()
    friend_ids = {friend['user_id'] for friend in friend_list}

    for user_id in reminders.keys():

        json_file_path = Path(f"{BINDINGS_DIR}/{user_id}.json")
        remaining_power=0
        if json_file_path.exists():
            with open(json_file_path, "r", encoding="utf-8") as file:
                binding_info = json.load(file)
            remaining_power = await query_electricity(binding_info)

        if int(user_id) not in friend_ids:
            # 如果用户不是好友，发送邮件提醒
            to_email = f"{user_id}@qq.com"
            subject = "邮件定时提醒：电量余额"
            body = f"您当前的电量余额为：{remaining_power}。"
            send_email(to_email, subject, body)
            continue 

        await bot.send_private_msg(user_id=int(user_id), message=f"定时提醒：当前剩余电量余额为 {remaining_power} 。")

# 这是个test
# @scheduler.scheduled_job("cron", hour=8, minute=1)
# async def test_email():
#     bot = get_bot()  # 获取 Bot 实例
#     json_file_path = Path(f"{BINDINGS_DIR}/3194771270.json")
#     remaining_power=0
#     if json_file_path.exists():
#         with open(json_file_path, "r", encoding="utf-8") as file:
#             binding_info = json.load(file)
#         remaining_power = await query_electricity(binding_info)

#     print(remaining_power)
#     to_email = "3194771270@qq.com"
#     subject = "电量余额提醒"
#     body = f"您当前的电量余额为：{remaining_power}。"
#     send_email(to_email, subject, body)


test_for_email_command = on_command("内测功能")

# 定义存储内测用户QQ号的JSON文件路径
EMAIL_USERS_FILE = Path("test_email_users.json")

def load_email_users():
    if EMAIL_USERS_FILE.exists():
        with open(EMAIL_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_email_users(users):
    with open(EMAIL_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

test_email_users = load_email_users()

@test_for_email_command.handle()
async def handle_test_for_email_command(bot: Bot, event: Event):
    friend_list = await bot.get_friend_list()
    friend_ids = {friend['user_id'] for friend in friend_list}
    user_id = event.get_user_id()  # 获取触发指令的用户QQ号
    
    # 检查是否是好友
    if int(user_id) not in friend_ids:
        await bot.send(event, message=f"用户安全起见，只有添加bot为好友才能使用内测功能")
        return
    
    # 检查是否已经在列表中
    if user_id not in test_email_users:
        test_email_users.append(user_id)  # 将用户QQ号存入列表
        save_email_users(test_email_users)  # 保存到JSON文件
        await bot.send(event, message=f"已成功将您的QQ号 {user_id} 添加到内测功能体验列表！")
    else:
        await bot.send(event, message=f"您的QQ号 {user_id} 已经在内测功能体验列表中，无需重复添加。")