# Spec Delta

## Purpose

定义 GeoPub 向 GeoServer 发布 SLD 样式的能力：上传/更新样式、将样式绑定为图层默认样式，以及不触碰任何图层的「仅上传」模式。覆盖 `geopub style` 命令与 Web 样式发布接口的可观察行为。

## ADDED Requirements

### Requirement: 样式上传与更新

系统 SHALL 将指定目录（含子目录）下的全部 `.sld` 文件上传到 GeoServer 的目标工作空间：样式不存在时创建，已存在时原地更新；单个样式上传失败 SHALL 报告该样式的失败原因（含服务端原始错误）且不中断其余样式的处理。目录下没有任何 `.sld` 文件时 SHALL 提示后正常结束（不视为错误）。

#### Scenario: 首次上传创建样式
- **WHEN** 目标工作空间中不存在与 SLD 文件同名的样式
- **THEN** 创建该样式，结果标记为「发布」（created）

#### Scenario: 已存在样式原地更新
- **WHEN** 目标工作空间中已存在同名样式
- **THEN** 更新该样式内容，结果标记为「更新」（updated），不删除重建

#### Scenario: 空目录不视为错误
- **WHEN** 指定目录下没有任何 `.sld` 文件
- **THEN** 输出提示信息并以成功状态结束

#### Scenario: 单个样式失败不影响其余
- **WHEN** 目录中某个 SLD 上传失败（如内容非法、服务端写盘错误）
- **THEN** 报告该样式的失败详情与 GeoServer 原始响应，其余样式继续处理

### Requirement: 默认绑定图层行为

未指定仅上传模式时，系统 SHALL 在上传/更新样式后将其绑定为图层默认样式：给定样式-图层映射文件时按映射绑定（一对多）；未给映射文件时按「同名图层」回退绑定。目标图层在 GeoServer 中不存在时 SHALL 将该次绑定标记为跳过并提示先发布图层，不影响其他样式。

#### Scenario: 无映射时同名回退绑定
- **WHEN** 未提供映射文件且存在与样式同名的图层
- **THEN** 该样式被绑定为同名图层的默认样式

#### Scenario: 映射一对多绑定
- **WHEN** 映射文件中某样式对应多个图层
- **THEN** 该样式被依次绑定为每个映射图层的默认样式

#### Scenario: 图层不存在时跳过绑定
- **WHEN** 绑定目标图层在 GeoServer 中不存在
- **THEN** 该次绑定标记为跳过（skipped）并提示先执行图层发布，其余绑定继续

### Requirement: 仅上传样式模式

系统 SHALL 提供「仅上传样式」模式（`geopub style --styles-only`，或 Web 接口 `styles_only=true`）：该模式只执行样式的创建/更新，MUST NOT 读取或修改任何图层（不检查图层是否存在、不修改图层默认样式），输出 SHALL 为样式级汇总（新增/更新/失败计数），不输出绑定结果与「请先发布图层」类提示。该标志 MUST 支持通过配置文件 `[style].styles_only` 启用，优先级为命令行显式值 > 配置文件 > 默认关闭。

#### Scenario: 仅上传模式不触碰图层
- **WHEN** 以仅上传模式执行样式发布
- **THEN** 目录下全部 SLD 被创建/更新，且无任何图层被查询或修改，输出为样式级汇总

#### Scenario: 通过配置文件启用
- **WHEN** 配置文件设置 `[style].styles_only = true` 且命令行未显式给出该标志
- **THEN** 以仅上传模式执行

#### Scenario: 显式关闭覆盖配置
- **WHEN** 配置文件设置 `[style].styles_only = true` 且命令行给出 `--no-styles-only`
- **THEN** 以默认绑定模式执行

### Requirement: 仅上传模式与映射文件互斥

仅上传模式与样式-图层映射文件 SHALL 互斥：两者同时指定（命令行或配置文件任一来源）时，系统 MUST 在执行任何 GeoServer 请求前报错并以非零状态退出。

#### Scenario: 同时给出标志与映射文件时拒绝执行
- **WHEN** 同时指定 `--styles-only` 与 `--file-path`（或配置 `[style].file_path` 非空）
- **THEN** 输出互斥错误说明，退出码非零，未向 GeoServer 发出任何写请求
