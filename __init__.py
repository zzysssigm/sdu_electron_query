from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from . import __main__ as __main__

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="sdu_electron_query",
    description="SDU青岛校区用于进行电费查询和定时提醒的插件",
    usage="/电费help -> 唤出使用说明\n"\
        "/电费绑定 -> 绑定账户和宿舍\n"\
        "/电费查询 -> 查询当前电费余额\n"\
        "/定时提醒 -> 每晚九点定时私信发送电量余额\n"\
        '/取消提醒 -> 取消提醒\n'
        '/电费解绑 -> 解除账户绑定\n',
    config=Config,
)

config = get_plugin_config(Config)

