# MFLAC → MP3 一键转换

带图形界面的 QQ 音乐 `.mflac` 批量/单文件转换工具，自动解密并输出 MP3。

## 功能

- 目录批量转换：`.mflac` → 解密 → `.mp3`
- 拖拽单文件：拖入 `.mflac` 自动转换到桌面
- 自动安装依赖：Python、qmdec、ffmpeg（通过 winget / pip，无需手动配置）
- 记住上次使用的目录路径（按用户保存在 `~/.mflac_mp3_ui/ui_config.json`）

## 使用前准备

1. **以管理员身份**运行本软件
2. **以管理员身份**打开并登录 **QQ 音乐**（需 VIP，且保持运行）
3. 首次使用点击 **「自动安装依赖」**，等待安装完成
4. 若 Python 刚装好但提示未找到，**关闭软件重新打开**后再点一次

## 快速开始（推荐：exe）

1. 到 [Releases](release/) 下载 `mflac_mp3_ui.exe`
2. 双击运行（建议右键 → 以管理员身份运行）
3. 点「自动安装依赖」→ 设置源目录 →「开始转换」

## 从源码运行

需要 Windows 10/11，已安装 Python 3.10+（可选，exe 会自动安装）。

```bash
pip install -r requirements.txt
python mflac_mp3_ui.py
```

## 打包 exe

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name mflac_mp3_ui --hidden-import windnd mflac_mp3_ui.py
```

产物在 `dist/mflac_mp3_ui.exe`。

## 目录说明

| 路径 | 说明 |
|------|------|
| `mflac_mp3_ui.py` | 主程序源码 |
| `release/mflac_mp3_ui.exe` | 预编译可执行文件 |
| `build_exe.bat` | Windows 一键打包脚本 |

## 工作原理

1. 使用 [qmdec](https://github.com/Sophomoresty/qmdec) 从本机 QQ 音乐进程获取凭证并解密 `.mflac`
2. 使用 ffmpeg 将解密后的 FLAC 转为 MP3
3. 若 qmdec 不可用，会尝试 [qmc-decoder](https://github.com/ownlight6/qmc-decoder) 作为备用

## 常见问题

**解密失败 / empty ekey**  
- 确认 QQ 音乐已登录 VIP  
- 确认 QQ 音乐与本软件都以管理员运行  
- 重新点「自动安装依赖」

**Python 安装后仍找不到**  
- 关闭软件重新打开（winget 安装后 PATH 需刷新）

**qmdec 安装失败**  
- 新版已改为从 GitHub 压缩包安装，不依赖 git

## 免责声明

- 本工具仅供**已合法获得**的音频文件做格式转换与学习研究
- `.mflac` 为 QQ 音乐加密格式，解密需本机 QQ 音乐授权
- 请勿用于盗版或商业用途；使用者自行承担法律责任

## 致谢

- [Sophomoresty/qmdec](https://github.com/Sophomoresty/qmdec)
- [ownlight6/qmc-decoder](https://github.com/ownlight6/qmc-decoder)
- [Gyan.FFmpeg](https://www.gyan.dev/ffmpeg/builds/)

## License

MIT
