# 安装包的中文语言包

**当前状态：已随仓库提供** `ChineseSimplified.isl`（21,516 字节，来自 Inno Setup 官方仓库
`jrsoftware/issrc` 的 `Files/Languages/`，由 Zhenghan Yang (Kira) 维护，UTF-8）。
`installer.iss` 在**脚本目录下存在**该文件时把「中文」加入语言列表，并且**列为第一项**：

```
[Languages]
#if FileExists(AddBackslash(SourcePath) + "ChineseSimplified.isl")
Name: "chinese"; MessagesFile: "ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"
```

Inno Setup 的语言列表**第一项就是安装向导的默认语言**，所以中文用户双击安装包直接看到
中文向导；英文用户可在语言页切换。安装时选择的语言还会写入注册表，供应用首次运行继承
（见 PRD D14）——例如选了 English，装完首次启动就是英文界面。

## 为什么需要单独放这个文件

Inno Setup 官方安装包只带英文与 29 种其它语言（`Languages\` 目录），**不含简体中文**；
简体中文是官方仓库里的用户贡献翻译，不随安装程序分发。所以要么随仓库带上，要么就没有
中文安装界面——但**应用本身**的中文界面不受影响（没有该文件时安装程序只用英文，
首次运行的语言落到主机语言）。

## 更新或替换

从 Inno Setup 官方仓库下载同名文件覆盖即可（`Files/Languages/ChineseSimplified.isl`）：
`https://github.com/jrsoftware/issrc`

替换后建议重新跑一遍测试：`tests/test_release.py::test_bundled_chinese_language_file_is_usable`
会校验它必须是 UTF-8、无 BOM、含 `[LangOptions]` / `LanguageName` / `LanguageID` /
`LanguageCodePage` 以及向导按钮文案，避免把一个坏文件带进安装包。

## 注意

- 文件受其自身许可证约束，随仓库分发前请确认许可条款；
- 编译**不依赖**它：删掉该文件后 `ISCC.exe packaging\installer.iss` 仍能正常出包，
  只是安装界面只有英文。

