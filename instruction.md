# 振动台停摆后的衰减曲线复原

振动台在一次夹具碰撞后只留下了零散位移采样，设备的激振频率、阻尼和静平衡位置都没有
随记录保存。工程师需要先把这条曲线反演成可外推的模型，再交给下一轮扫频使用。
`/app/identify.py` 现在只会输出一条没有衰减的余弦，请把它改成真正从样本恢复运动的程序。

入口保持 `python3 /app/identify.py <input.json> <output.json>`。计算使用镜像内标准库，
既不读取测试目录，也不调用外部数值服务。

## 采样记录

输入顶层只有 `schema`、`samples`、`queries`、`noise_floor`：

```json
{
  "schema": "damped-trace-v1",
  "samples": [
    {"t": 0.0, "x": 2.74},
    {"t": 0.37, "x": 2.12}
  ],
  "queries": [0.0, 1.4, 5.1],
  "noise_floor": 0.0005
}
```

`samples` 保存 12 到 64 条采样；每条仅由 `t` 与 `x` 两个字段组成。时间与位移都是有限数值，
时间落在 0 到 120 的时间坐标并严格递增，位移可正可负。`queries` 有 1 到 24 个有限时间，
同样落在 0 到 120 的时间坐标且严格递增。`noise_floor` 位于 `[0, 0.05]`；逻辑真假
不能当实数输入。

## 物理模型

采样应能用欠阻尼单自由度响应描述：

`x(t) = offset + amplitude * exp(-damping_rate*t) * cos(omega*t + phase)`。

其中 `amplitude` 大于零，`damping_rate` 不小于零且小于 `omega`，`omega` 大于零，
`phase` 放在 `(-pi, pi]`，`offset` 为有限数值。模型在全部样本上的均方根残差不能超过
`noise_floor`；超过时说明采样不属于这条可接受模型，应拒绝而不应猜测参数。

一个完整自由振荡周期后的机械能保留比例为
`exp(-4*pi*damping_rate/omega)`。该比例只由衰减率和角频率决定，不能拿样本首末振幅
简单相除代替。

## 交付格式

辨识成功后，输出包含辨识状态、`model`、`predictions`、一周期 `energy_ratio` 和 `rms`。`status` 为
`"ok"`；`model` 恰好有 `amplitude`、`damping_rate`、`omega`、`phase`、`offset`；
`predictions` 按查询顺序给出对象，每项恰好有 `t` 与 `x`。所有浮点结果保留六位小数。

若输入不合规，或残差高过门槛，就别留下文件；标准错误给出
`REFUSED: <原因>`，退出码为 2。顺利结束时不要打印内容；输出文件采用键排序、
无额外空格的 JSON，末字符为换行。
