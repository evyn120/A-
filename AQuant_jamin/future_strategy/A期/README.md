# 投资分析工具

贵金属及期货多维度投资分析平台，基于 Streamlit 构建。

## ✨ 功能特性

### 📊 行情总览
- 贵金属实时报价（黄金、白银、铂金）
- K线走势图（日K/周K/月K可切换）
- 自定义期货品种添加/删除
- 成交量展示

### 📈 技术分析
- **MACD**：DIF/DEA/柱状图分析，金叉死叉判断，具体结论输出
- **KDJ**：K/D/J值分析，超买超卖判断，金叉死叉检测
- **RSI**：相对强弱指标，超买超卖区间判断
- **均线系统**：MA5/MA10/MA20/MA60/MA120/MA250，多头/空头排列判断
- **缠论分析**：分型识别、笔段划分，方向性判断
- **波浪理论**：推动浪/调整浪识别，浪型状态判断
- **信号汇总**：整体技术面判断（偏多/偏空/震荡）

### 💰 资金面分析
- **量价分析**：量增价涨/量缩价涨等关系判断
- **OBV指标**：能量潮分析，资金流向判断
- **MFI指标**：资金流量指标，超买超卖判断
- **量价背离检测**：顶背离/底背离预警

### 📰 消息面分析
- **新闻聚合**：从Google News、Finviz等来源爬取黄金相关新闻
- **事件日历**：重大经济事件（FOMC、非农、CPI等）
- **情感分析**：基于关键词的新闻正面/负面/中性判断

### 🎯 投资预测
- **博主观点**：从Gold-Eagle等网站爬取分析师观点
- **综合评分**：技术面40% + 资金面25% + 消息面25% + 博主观点10%
- **方向判断**：偏多/偏空/震荡
- **置信度评估**：基于各维度一致性判断

## 🚀 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行应用

```bash
streamlit run app.py
```

## 📁 项目结构

```
投资分析工具/
├── .streamlit/config.toml   # 隐藏sidebar导航
├── app.py                    # 单页面路由入口
├── config.py                 # 配置文件
├── requirements.txt          # 依赖列表
├── services/                 # 数据服务
│   ├── market_data.py        # 行情数据获取
│   ├── technical_analysis.py # 技术指标计算 + 结论生成
│   ├── chan_theory.py        # 缠论分析 + 方向判断
│   ├── elliott_wave.py       # 波浪理论 + 方向判断
│   ├── fund_flow.py          # 资金面分析（OBV/MFI/量价）
│   ├── blogger_scraper.py    # 博主观点爬取
│   ├── news_scraper.py       # 新闻爬取
│   └── sentiment.py          # 情感分析
├── views/                    # 页面视图
│   ├── home.py               # 首页（卡片导航）
│   ├── market_overview.py    # 行情总览
│   ├── technical.py          # 技术分析
│   ├── fund_flow.py          # 资金面
│   ├── news.py               # 消息面
│   └── prediction.py         # 投资预测
└── utils/
    └── chart_helper.py       # 图表绘制（plotly_white主题）
```

## ⚠️ 免责声明

本工具仅供学习参考，不构成任何投资建议。投资有风险，入市需谨慎。
