# SurfingTile：禁用自动更新

## 模块侧

安装或升级模块时，只要检测到 `com.github.surfing` 或旧包名 `com.surfing.tile`，
就保留该应用，不比较远端/打包版本，不覆盖、不自动卸载迁移。首次安装应用仍然
可用；没有应用的模块升级场景保留音量键选择。安装命令不再带替换标记 `-r`。

## 应用侧

`app/version/com.github.surfing/SurfingTile_7.0.0_no_update.apk` 是基于原版
7.0.0 的重打包版本，版本名 `7.0.0-no-update`、包名不变。

- 启动更新检查不再发送请求，保留主线程完成回调，不显示新版本标记。
- 更新管理器的元数据请求、APK 下载与下载任务入口被禁用。
- 原软件更新页面显示禁用说明，不再显示检查、下载、安装按钮。
- 订阅更新、代理配置、WebView 更新与模块核心更新逻辑不在本次修改范围。

build.sh 优先打包这个定制 APK。原版 APK 仍保留为可验证的补丁输入。
更新元数据 release.json 保留历史信息，但定制版的更新检查不会再读取它。

## 安装和签名

已安装的原版不会被模块自动替换，所以要启用应用侧修改，需要用户自行切换到
这个 APK。定制版使用新的签名证书，不能直接覆盖原版；先备份应用设置，再卸载
原版后安装。卸载会影响应用自身数据，本次没有在任何设备上执行安装或卸载。

Android 更新安装会比较签名证书，见
[官方签名说明](https://developer.android.com/studio/publish/app-signing)。

定制签名证书 SHA-256：
`76bbba3f8f95eaba565ac7554d997dc879ad72c56a5b929ba21c96db8a1765b6`

APK SHA-256：
`e5abe198dd6bbfb3ff8579c2e5954905d41feaae186ad17fb8b0b2d9a9d9d61b`

私钥保留在本次本地工作区的 work/signing 中，没有提交到 GitHub。后续定制构建
如需覆盖此版本，必须使用同一个私钥签名。

## 补丁复现

最新 APK 对应的完整应用源码尚未找到。仓库另有旧版源码归档，不能作为当前
7.0.0 的直接构建输入。本次修改的是反汇编方法，不是重新编译新版 Java 工程。

使用 Apktool 3.0.3、Java 17、Python 3：

```sh
java -jar apktool.jar d app/version/com.github.surfing/SurfingTile_7.0.0_release.apk -o tile-decoded
python3 .github/tools/disable_tile_updates.py app/version/com.github.surfing/SurfingTile_7.0.0_release.apk tile-decoded
java -jar apktool.jar b tile-decoded -o SurfingTile_no_update_unsigned.apk
```

脚本验证原 APK 的 SHA-256，只允许已审核的 7.0.0 构建；类名和方法来自该版本
混淆后的 DEX，不适用于其他版本。重打包后必须对齐并使用自己的密钥签名。
本次使用 uber-apk-signer 1.3.0 完成对齐、签名和验证。

## 验证

19 项主机回归测试通过，包括已有应用保留、旧包名保留、首次安装保留、未安装
时跳过/选择安装。安装脚本和构建脚本语法检查通过。

APK 已成功重打包，签名 v3 与 zipalign 验证通过；重新反汇编确认目标检查与
下载路径已禁用，原 APK 的 24 个资源资产及原生库文件内容保持一致。
没有连接 Android 测试设备，尚未验证实际启动、Root 授权、磁贴、配置编辑及
签名变化是否影响应用内部校验；这是待真机验收的定制构建。
