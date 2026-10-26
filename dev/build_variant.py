# -*- coding: utf-8 -*-
"""源码运行时的「变体垫片」。

打包版由 ``scripts/build_onedir.ps1`` 在打包前生成 ``packaging/build_variant.py``，
``pet/config.py::_app_dir_name()`` 靠它把数据目录区分成
``%APPDATA%\\dsh-pet-standalone-<variant>``。

源码直接 ``python -m pet`` 时没有这个模块，会回落到共享目录
``%APPDATA%\\dsh-pet-standalone``——配置、会话、角色包、凭据引用全部对不上。

本文件声明 ``VARIANT = "webm-chat"``，让源码版复用安装版的数据目录：

    %APPDATA%\\dsh-pet-standalone-webm-chat

生效方式（二选一，仓库里两条都配好了）：
1. ``dev/run-src.bat`` 把本目录加进 ``PYTHONPATH``；
2. ``.venv/Lib/site-packages/_dsh_pet_dev.pth`` 写死本目录（开机自启不经过 bat，
   也能 import 到）。

⚠️ 不要把它改名成 ``build_variant.py`` 放进 ``packaging/``：那是打包脚本生成的
产物（已被 .gitignore 忽略），两边同时存在会让人搞不清哪个生效。
"""

VARIANT = "webm-chat"
