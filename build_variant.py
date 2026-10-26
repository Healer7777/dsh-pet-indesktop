# -*- coding: utf-8 -*-
"""源码运行时的「变体垫片」——让源码版复用安装版的数据目录。

背景
----
打包版由 ``scripts/build_onedir.ps1`` 在打包前生成 ``packaging/build_variant.py``，
``pet/config.py::_app_dir_name()`` 靠它把数据目录区分成
``%APPDATA%\\dsh-pet-standalone-<variant>``。

源码直接 ``python -m pet`` 时没有这个模块，会回落到共享目录
``%APPDATA%\\dsh-pet-standalone``——配置、会话、角色包、凭据引用全部对不上，
表现为"设置全丢了、Key 也没了"。

本文件声明 ``VARIANT = "webm-chat"``，让源码版读同一个目录：

    %APPDATA%\\dsh-pet-standalone-webm-chat

为什么放在仓库根目录
--------------------
``python -m pet`` 启动时 ``sys.path[0]`` 就是当前工作目录；开机自启命令
（``pet/autostart.py::_win_command``）也是 ``cmd /c start /D <仓库根> pythonw -m pet``。
放在根目录，**不管 venv 是否重建、PYTHONPATH 是否设置**，``import build_variant``
都能命中——比只靠 .pth 或 bat 里的环境变量更抗折腾。

⚠️ 不要把它复制成 ``packaging/build_variant.py``：那是打包脚本生成的产物
（已在 .gitignore 里），两边同时存在会让人搞不清哪个生效。
"""

VARIANT = "webm-chat"
