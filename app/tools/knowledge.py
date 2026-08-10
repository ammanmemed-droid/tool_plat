"""内置知识库（数据层）。

生产环境中应替换为结构化数据库 / OEM 文档检索 / 案例工单系统，
此处以内存数据模拟，保证工具行为符合各 SKILL.md 的规则与兜底语义。
"""

# ---------------------------------------------------------------------------
# 通用 OBD-II DTC 数据库：dtc_code -> 背景上下文
# ---------------------------------------------------------------------------
GENERIC_DTC_DB: dict[str, dict] = {
    "P0171": {
        "dtc_description": "System too lean (Bank 1)，发动机 1 列混合气过稀",
        "system": "发动机系统",
        "subsystem": "燃油修正 / 空燃比控制",
        "trigger_condition": "ECU 检测到 Bank 1 长期燃油修正值超过标定阈值，判定混合气过稀",
        "related_parts": ["MAF 空气流量传感器", "氧传感器", "真空管路", "进气管路", "燃油泵 / 燃油压力调节相关部件", "PCV 阀及管路"],
        "related_datastreams": ["短期燃油修正", "长期燃油修正", "MAF 数值", "氧传感器电压"],
    },
    "P0300": {
        "dtc_description": "Random/Multiple Cylinder Misfire Detected，随机/多缸失火",
        "system": "发动机系统",
        "subsystem": "点火 / 燃烧控制",
        "trigger_condition": "ECU 通过曲轴转速波动检测到多个气缸存在失火，且超过排放/催化保护阈值",
        "related_parts": ["火花塞", "点火线圈", "喷油嘴", "缸压相关部件", "真空管路"],
        "related_datastreams": ["失火计数", "发动机转速", "短期燃油修正", "长期燃油修正"],
    },
    "P0420": {
        "dtc_description": "Catalyst System Efficiency Below Threshold (Bank 1)，催化转换器效率低于阈值（1 列）",
        "system": "发动机系统 / 排放系统",
        "subsystem": "三元催化后处理",
        "trigger_condition": "ECU 对比前后氧传感器信号，判定催化器储氧能力低于标定阈值",
        "related_parts": ["催化转换器", "前氧传感器", "后氧传感器", "排气系统"],
        "related_datastreams": ["前氧传感器电压", "后氧传感器电压", "催化器温度"],
    },
    "P0430": {
        "dtc_description": "Catalyst System Efficiency Below Threshold (Bank 2)，催化转换器效率低于阈值（2 列）",
        "system": "发动机系统 / 排放系统",
        "subsystem": "三元催化后处理",
        "trigger_condition": "ECU 对比 Bank 2 前后氧传感器信号，判定催化器储氧能力低于标定阈值",
        "related_parts": ["催化转换器", "前氧传感器", "后氧传感器", "排气系统"],
        "related_datastreams": ["前氧传感器电压", "后氧传感器电压", "催化器温度"],
    },
    "P0442": {
        "dtc_description": "EVAP Emission Control System Leak Detected (small leak)，蒸发排放系统小泄漏",
        "system": "发动机系统 / 排放系统",
        "subsystem": "EVAP 蒸发排放控制",
        "trigger_condition": "ECU 对 EVAP 系统加压/抽真空检漏时检测到小直径级别的泄漏",
        "related_parts": ["油箱盖", "EVAP 碳罐", "EVAP 通风阀", "EVAP 管路"],
        "related_datastreams": ["EVAP 系统压力", "通风阀状态", "净化阀占空比"],
    },
    "U0100": {
        "dtc_description": "Lost Communication with ECM/PCM，与发动机控制模块失去通信",
        "system": "车身网络 / 通信系统",
        "subsystem": "CAN 总线通信",
        "trigger_condition": "总线上其他模块在规定时间内未收到 ECM/PCM 的报文",
        "related_parts": ["CAN 通信线路", "发动机控制模块", "控制模块供电 / 接地"],
        "related_datastreams": ["CAN 总线电压", "模块在线状态"],
    },
    "U0121": {
        "dtc_description": "Lost Communication with Anti-Lock Brake System Control Module，与 ABS 控制模块失去通信",
        "system": "车身网络 / 通信系统",
        "subsystem": "CAN 总线通信",
        "trigger_condition": "总线上其他模块在规定时间内未收到 ABS 模块的报文",
        "related_parts": ["CAN 通信线路", "ABS 控制模块", "控制模块供电 / 接地"],
        "related_datastreams": ["CAN 总线电压", "模块在线状态"],
    },
    "B1325": {
        "dtc_description": "Control Module Power Circuit Low Voltage，控制模块供电电压过低",
        "system": "车身电气系统",
        "subsystem": "供电 / 电源管理",
        "trigger_condition": "车身控制模块检测到供电电压低于工作阈值",
        "related_parts": ["蓄电池", "发电机", "主供电线路", "保险丝 / 继电器"],
        "related_datastreams": ["蓄电池电压", "发电电压"],
    },
}

# 品牌专属 DTC 资料：brand -> dtc_code -> 覆盖字段
BRAND_DTC_DB: dict[str, dict[str, dict]] = {
    "宝马": {
        "P0171": {
            "dtc_description": "宝马体系下 P0171 常指向进气系统漏气或曲轴箱通风（PCV）异常导致的混合气过稀",
            "related_parts": ["气门室盖 PCV 膜片", "进气管路", "真空管路", "MAF 空气流量传感器", "氧传感器"],
        },
    },
    "奔驰": {},
    "大众": {},
}

# 品牌别名归一化
BRAND_ALIASES = {
    "bmw": "宝马", "宝马": "宝马",
    "benz": "奔驰", "mercedes": "奔驰", "奔驰": "奔驰",
    "vw": "大众", "volkswagen": "大众", "大众": "大众",
}

# ---------------------------------------------------------------------------
# 结构化原因数据：dtc_code -> 候选原因（structured_reason_data）
# ---------------------------------------------------------------------------
STRUCTURED_CAUSE_DB: dict[str, list[dict]] = {
    "P0171": [
        {"cause_id": "CAUSE_ENGINE_001", "cause_name": "进气系统真空泄漏", "related_parts": ["真空管路", "进气管路", "PCV 阀及管路"], "source_reference": "DTC2FIX_CAUSE_001"},
        {"cause_id": "CAUSE_ENGINE_002", "cause_name": "MAF 空气流量传感器脏污或故障", "related_parts": ["MAF 空气流量传感器"], "source_reference": "DTC2FIX_CAUSE_002"},
        {"cause_id": "CAUSE_ENGINE_003", "cause_name": "燃油压力不足", "related_parts": ["燃油泵", "燃油滤清器", "燃油压力调节相关部件"], "source_reference": "DTC2FIX_CAUSE_003"},
        {"cause_id": "CAUSE_ENGINE_004", "cause_name": "前氧传感器老化信号漂移", "related_parts": ["氧传感器"], "source_reference": "DTC2FIX_CAUSE_004"},
    ],
    "P0300": [
        {"cause_id": "CAUSE_IGNITION_001", "cause_name": "火花塞磨损或间隙异常", "related_parts": ["火花塞"], "source_reference": "DTC2FIX_CAUSE_010"},
        {"cause_id": "CAUSE_IGNITION_002", "cause_name": "点火线圈性能下降", "related_parts": ["点火线圈"], "source_reference": "DTC2FIX_CAUSE_011"},
        {"cause_id": "CAUSE_FUEL_001", "cause_name": "喷油嘴堵塞或雾化不良", "related_parts": ["喷油嘴"], "source_reference": "DTC2FIX_CAUSE_012"},
        {"cause_id": "CAUSE_ENGINE_001", "cause_name": "进气系统真空泄漏", "related_parts": ["真空管路", "进气管路"], "source_reference": "DTC2FIX_CAUSE_001"},
    ],
    "P0420": [
        {"cause_id": "CAUSE_EMISSION_001", "cause_name": "催化转换器效率下降", "related_parts": ["催化转换器", "排气系统"], "source_reference": "DTC2FIX_CAUSE_020"},
        {"cause_id": "CAUSE_EMISSION_002", "cause_name": "后氧传感器信号异常", "related_parts": ["后氧传感器"], "source_reference": "DTC2FIX_CAUSE_021"},
    ],
    "P0430": [
        {"cause_id": "CAUSE_EMISSION_001", "cause_name": "催化转换器效率下降", "related_parts": ["催化转换器", "排气系统"], "source_reference": "DTC2FIX_CAUSE_020"},
    ],
    "P0442": [
        {"cause_id": "CAUSE_EVAP_001", "cause_name": "油箱盖密封不良", "related_parts": ["油箱盖"], "source_reference": "DTC2FIX_CAUSE_030"},
        {"cause_id": "CAUSE_EVAP_002", "cause_name": "EVAP 管路或碳罐泄漏", "related_parts": ["EVAP 碳罐", "EVAP 管路", "EVAP 通风阀"], "source_reference": "DTC2FIX_CAUSE_031"},
    ],
    "U0100": [
        {"cause_id": "CAUSE_NETWORK_001", "cause_name": "CAN 总线线路故障", "related_parts": ["CAN 通信线路"], "source_reference": "DTC2FIX_CAUSE_040"},
        {"cause_id": "CAUSE_NETWORK_002", "cause_name": "发动机控制模块供电或接地异常", "related_parts": ["控制模块供电 / 接地", "保险丝 / 继电器"], "source_reference": "DTC2FIX_CAUSE_041"},
    ],
    "U0121": [
        {"cause_id": "CAUSE_NETWORK_001", "cause_name": "CAN 总线线路故障", "related_parts": ["CAN 通信线路"], "source_reference": "DTC2FIX_CAUSE_040"},
        {"cause_id": "CAUSE_NETWORK_003", "cause_name": "ABS 控制模块供电或接地异常", "related_parts": ["ABS 控制模块", "控制模块供电 / 接地"], "source_reference": "DTC2FIX_CAUSE_042"},
    ],
}

# 原厂文档检索结果（single_dtc 降级第二级）
OEM_DOC_CAUSE_DB: dict[str, list[dict]] = {
    "B1325": [
        {"cause_name": "蓄电池老化或充电系统异常", "related_parts": ["蓄电池", "发电机"], "source_reference": "OEM_DOC_ELEC_008"},
    ],
}

# 症状 -> 结构化症状-原因数据（symptom_case 且 no_dtc）
SYMPTOM_CAUSE_DB: list[dict] = [
    {"keywords": ["怠速抖动", "抖动", "怠速不稳"], "system": "发动机系统",
     "causes": [
         {"cause_id": "CAUSE_SYM_001", "cause_name": "节气门积碳", "related_parts": ["节气门"], "source_reference": "SYM2CAUSE_001"},
         {"cause_id": "CAUSE_IGNITION_001", "cause_name": "火花塞磨损或间隙异常", "related_parts": ["火花塞"], "source_reference": "DTC2FIX_CAUSE_010"},
         {"cause_id": "CAUSE_ENGINE_001", "cause_name": "进气系统真空泄漏", "related_parts": ["真空管路", "进气管路"], "source_reference": "DTC2FIX_CAUSE_001"},
     ]},
    {"keywords": ["冷启动困难", "启动困难", "打不着"], "system": "发动机系统",
     "causes": [
         {"cause_id": "CAUSE_SYM_002", "cause_name": "燃油压力不足", "related_parts": ["燃油泵", "燃油滤清器"], "source_reference": "SYM2CAUSE_002"},
         {"cause_id": "CAUSE_SYM_003", "cause_name": "蓄电池电量不足", "related_parts": ["蓄电池"], "source_reference": "SYM2CAUSE_003"},
     ]},
    {"keywords": ["空调不制冷", "不制冷"], "system": "空调系统",
     "causes": [
         {"cause_id": "CAUSE_SYM_004", "cause_name": "制冷剂不足或泄漏", "related_parts": ["空调管路", "冷凝器"], "source_reference": "SYM2CAUSE_004"},
         {"cause_id": "CAUSE_SYM_005", "cause_name": "空调压缩机不工作", "related_parts": ["空调压缩机", "压缩机电磁离合器"], "source_reference": "SYM2CAUSE_005"},
     ]},
]

# ---------------------------------------------------------------------------
# 结构化维修知识（检查项）：cause_id -> 候选检查项
# ---------------------------------------------------------------------------
STRUCTURED_CHECK_DB: dict[str, list[dict]] = {
    "CAUSE_ENGINE_001": [
        {"check_id": "CHECK_DS_001", "check_name": "读取燃油修正数据流", "check_type": "datastream",
         "check_goal": "通过长期/短期燃油修正值确认混合气是否确实偏稀", "structured_order": 1,
         "check_cost": "low", "required_tools": ["诊断仪"],
         "judgment_summary": "长期燃油修正 > +10% 判定为异常偏稀",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "长期燃油修正 > +10%", "result_interpretation": "混合气确实偏稀，继续定位泄漏点",
              "next_action": "continue_check", "next_check_id": "CHECK_SMOKE_001"},
             {"result_type": "normal", "judgment_condition": "燃油修正值在 ±10% 以内", "result_interpretation": "当前混合气正常，真空泄漏假设证据不足",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "数据流无法读取", "result_interpretation": "无法获取数据流", "next_action": "ask_user"},
         ]},
        {"check_id": "CHECK_SMOKE_001", "check_name": "进气系统烟雾测漏", "check_type": "manual",
         "check_goal": "定位进气系统具体泄漏点", "structured_order": 2,
         "prerequisite_check_ids": ["CHECK_DS_001"],
         "check_cost": "medium", "required_tools": ["烟雾测漏仪"],
         "judgment_summary": "烟雾从某处逸出即为泄漏点",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "发现烟雾逸出点", "result_interpretation": "确认真空泄漏位置",
              "next_action": "enter_repair_planning",
              "confirmed_cause": {"cause_id": "CAUSE_ENGINE_001", "cause_name": "进气系统真空泄漏"}},
             {"result_type": "normal", "judgment_condition": "无烟雾逸出", "result_interpretation": "未发现泄漏点，真空泄漏假设不成立",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "设备不可用", "result_interpretation": "无法完成测漏", "next_action": "human_support"},
         ]},
    ],
    "CAUSE_ENGINE_002": [
        {"check_id": "CHECK_DS_002", "check_name": "MAF 数据流检查", "check_type": "datastream",
         "check_goal": "对比怠速/加速工况 MAF 实际值与标准值，判断计量是否失准", "structured_order": 1,
         "check_cost": "low", "required_tools": ["诊断仪"],
         "judgment_summary": "怠速 MAF 明显低于标准范围视为异常",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "MAF 值偏离标准范围", "result_interpretation": "MAF 计量失准",
              "next_action": "enter_repair_planning",
              "confirmed_cause": {"cause_id": "CAUSE_ENGINE_002", "cause_name": "MAF 空气流量传感器脏污或故障"}},
             {"result_type": "normal", "judgment_condition": "MAF 值在标准范围", "result_interpretation": "MAF 工作正常",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "数据波动异常", "result_interpretation": "信号不稳定，需结合线路检查", "next_action": "ask_user"},
         ]},
    ],
    "CAUSE_ENGINE_003": [
        {"check_id": "CHECK_FUELP_001", "check_name": "燃油压力测试", "check_type": "measurement",
         "check_goal": "测量燃油轨实际压力，确认燃油供给是否不足", "structured_order": 1,
         "check_cost": "medium", "required_tools": ["燃油压力表"],
         "judgment_summary": "怠速油压低于厂家标准值判定异常",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "油压低于标准", "result_interpretation": "燃油压力不足成立",
              "next_action": "enter_repair_planning",
              "confirmed_cause": {"cause_id": "CAUSE_ENGINE_003", "cause_name": "燃油压力不足"}},
             {"result_type": "normal", "judgment_condition": "油压正常", "result_interpretation": "燃油供给正常",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "压力波动大", "result_interpretation": "供油不稳定，需进一步检查油泵电路", "next_action": "continue_check"},
         ]},
    ],
    "CAUSE_IGNITION_001": [
        {"check_id": "CHECK_SPARK_001", "check_name": "火花塞拆检", "check_type": "manual",
         "check_goal": "检查火花塞电极磨损、间隙与积碳情况", "structured_order": 1,
         "check_cost": "low", "required_tools": ["火花塞套筒", "塞尺"],
         "judgment_summary": "电极磨损严重或间隙超标判定异常",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "电极磨损 / 间隙超标", "result_interpretation": "火花塞达到更换条件",
              "next_action": "enter_repair_planning",
              "confirmed_cause": {"cause_id": "CAUSE_IGNITION_001", "cause_name": "火花塞磨损或间隙异常"}},
             {"result_type": "normal", "judgment_condition": "状态良好", "result_interpretation": "火花塞正常",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "无法拆检", "result_interpretation": "装配条件限制", "next_action": "human_support"},
         ]},
    ],
    "CAUSE_IGNITION_002": [
        {"check_id": "CHECK_COIL_001", "check_name": "点火线圈对调测试", "check_type": "manual",
         "check_goal": "通过对调点火线圈观察失火是否随缸转移，判断线圈性能", "structured_order": 2,
         "check_cost": "low", "required_tools": ["诊断仪"],
         "judgment_summary": "失火随线圈转移判定线圈故障",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "失火随缸转移", "result_interpretation": "点火线圈故障成立",
              "next_action": "enter_repair_planning",
              "confirmed_cause": {"cause_id": "CAUSE_IGNITION_002", "cause_name": "点火线圈性能下降"}},
             {"result_type": "normal", "judgment_condition": "失火不转移", "result_interpretation": "点火线圈正常",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "失火随机", "result_interpretation": "无法定位单缸问题", "next_action": "update_cause_ranking"},
         ]},
    ],
    "CAUSE_EMISSION_001": [
        {"check_id": "CHECK_CAT_001", "check_name": "前后氧传感器波形对比", "check_type": "datastream",
         "check_goal": "通过前后氧波形相似度评估催化器储氧能力", "structured_order": 1,
         "check_cost": "low", "required_tools": ["诊断仪"],
         "judgment_summary": "后氧波形跟随前氧快速波动说明催化效率下降",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "后氧跟随前氧波动", "result_interpretation": "催化器效率确实下降",
              "next_action": "enter_repair_planning",
              "confirmed_cause": {"cause_id": "CAUSE_EMISSION_001", "cause_name": "催化转换器效率下降"}},
             {"result_type": "normal", "judgment_condition": "后氧平稳", "result_interpretation": "催化器工作正常",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "波形受干扰", "result_interpretation": "需排查氧传感器本身", "next_action": "continue_check"},
         ]},
    ],
    "CAUSE_NETWORK_001": [
        {"check_id": "CHECK_CAN_001", "check_name": "CAN 总线电压与电阻测量", "check_type": "measurement",
         "check_goal": "测量 CAN-H/CAN-L 电压与终端电阻，判断总线物理层状态", "structured_order": 1,
         "check_cost": "low", "required_tools": ["万用表"],
         "judgment_summary": "终端电阻约 60Ω、CAN-H/L 电压在正常窗口判定正常",
         "result_branches": [
             {"result_type": "abnormal", "judgment_condition": "电阻或电压偏离标准", "result_interpretation": "总线线路存在断路/短路",
              "next_action": "enter_repair_planning",
              "confirmed_cause": {"cause_id": "CAUSE_NETWORK_001", "cause_name": "CAN 总线线路故障"}},
             {"result_type": "normal", "judgment_condition": "电阻电压正常", "result_interpretation": "总线物理层正常，转向模块供电检查",
              "next_action": "update_cause_ranking"},
             {"result_type": "inconclusive", "judgment_condition": "测量点不可达", "result_interpretation": "需要拆卸饰板或举升车辆", "next_action": "ask_user"},
         ]},
    ],
}

# 症状 -> 结构化检查项（symptom_case 场景补充）
SYMPTOM_CHECK_DB: list[dict] = [
    {"keywords": ["怠速抖动", "抖动", "怠速不稳"],
     "checks": [
         {"check_id": "CHECK_SYM_001", "check_name": "节气门开度与积碳目视检查", "check_type": "manual",
          "check_goal": "确认节气门是否积碳卡滞", "structured_order": 1, "check_cost": "low",
          "required_tools": ["手电筒"],
          "judgment_summary": "节气门边缘明显积碳判定异常",
          "result_branches": [
              {"result_type": "abnormal", "judgment_condition": "明显积碳", "result_interpretation": "节气门积碳成立",
               "next_action": "enter_repair_planning",
               "confirmed_cause": {"cause_id": "CAUSE_SYM_001", "cause_name": "节气门积碳"}},
              {"result_type": "normal", "judgment_condition": "洁净", "result_interpretation": "节气门正常",
               "next_action": "update_cause_ranking"},
              {"result_type": "inconclusive", "judgment_condition": "无法目视", "result_interpretation": "需拆卸进气管", "next_action": "ask_user"},
          ]},
     ]},
]

# ---------------------------------------------------------------------------
# 保养归零 SOP 资料库
# ---------------------------------------------------------------------------
MAINTENANCE_SOP_DB: list[dict] = [
    {"brand": "奔驰", "model": "C200", "years": ["2010", "2009", "2011"], "source_type": "exact_case",
     "source_confidence": "high",
     "steps": [
         {"step_no": 1, "instruction": "点火开关置于 1 档（ACC）。", "source_ref": "图1"},
         {"step_no": 2, "instruction": "通过方向盘左侧按键调出仪表总里程界面。", "source_ref": "图2"},
         {"step_no": 3, "instruction": "连续按仪表左侧调光按钮 3 次，听到提示音后仪表显示电压界面。", "source_ref": "图3"},
         {"step_no": 4, "instruction": "点火开关置于 2 档（ON），按方向盘下翻键进入 Service 保养菜单。", "source_ref": "图4"},
         {"step_no": 5, "instruction": "选择【整套保养】，长按 OK 键确认复位，仪表提示【保养已复位】。", "source_ref": "图5"},
     ]},
    {"brand": "宝马", "model": "3系", "years": ["2015", "2016", "2017", "2018"], "source_type": "exact_case",
     "source_confidence": "high",
     "steps": [
         {"step_no": 1, "instruction": "不踩刹车按一次启动按钮通电。", "source_ref": "图1"},
         {"step_no": 2, "instruction": "长按仪表左下角里程复位按钮约 10 秒，直至仪表出现保养项目菜单。", "source_ref": "图2"},
         {"step_no": 3, "instruction": "短按复位按钮切换选择【机油保养】项目。", "source_ref": "图3"},
         {"step_no": 4, "instruction": "长按复位按钮，仪表提示【复位？】，再次长按确认，显示【复位成功】。", "source_ref": "图4"},
     ]},
]

GENERIC_RESET_SOP: dict = {
    "source_type": "general_path",
    "source_confidence": "medium",
    "steps": [
        {"step_no": 1, "instruction": "连接诊断设备并进入车型选择界面，选择对应品牌、车型与年款。"},
        {"step_no": 2, "instruction": "进入【特殊功能】或【保养归零】功能菜单。"},
        {"step_no": 3, "instruction": "选择【机油保养归零】或对应保养项目，按设备提示操作。"},
        {"step_no": 4, "instruction": "设备提示操作成功后，启动车辆确认仪表保养提示已清除。"},
    ],
}

# ---------------------------------------------------------------------------
# 结构化维修知识：维修方案
# ---------------------------------------------------------------------------
REPAIR_KNOWLEDGE_DB: list[dict] = [
    {
        "keywords": ["进气系统真空泄漏", "进气泄漏", "真空泄漏"],
        "cause_id": "CAUSE_ENGINE_001",
        "solution_id": "RS_ENGINE_001",
        "solution_name": "修复进气泄漏点",
        "solution_description": "更换或修复烟雾测漏确认的泄漏部件（真空管、进气管垫、PCV 阀等）",
        "repair_method": "根据测漏结果定位泄漏部件：真空管破裂则更换新管并紧固卡箍；进气管垫老化则拆卸进气歧管更换密封垫；PCV 阀失效则更换 PCV 阀总成。装配后复测燃油修正值确认。",
        "parts": [
            {"part_name": "真空管路", "part_type": "oem", "price_estimate": "20 - 80 元", "source": "structured_repair_knowledge"},
            {"part_name": "进气歧管密封垫", "part_type": "oem", "price_estimate": "50 - 200 元", "source": "structured_repair_knowledge"},
        ],
        "labor": {"estimated_time": "0.5 - 2.0 小时", "source": "standard_repair_data", "source_confidence": "medium"},
        "cost": {"parts_cost": "20 - 280 元", "labor_cost": "100 - 400 元", "total_cost": "120 - 680 元", "currency": "CNY", "source": "case_work_order", "source_confidence": "medium"},
        "risk_level": "low",
        "post_repair_validation": "清除故障码后路试 10 公里以上，复扫确认 P0171 等故障码未复发，且长期燃油修正值回落至 ±10% 以内。若复发，需重新执行 Cause Ranking 排查其他候选原因。",
    },
    {
        "keywords": ["氧传感器损坏", "氧传感器故障", "前氧传感器老化", "后氧传感器信号异常"],
        "cause_id": "CAUSE_ENGINE_004",
        "solution_id": "RS_ENGINE_004",
        "solution_name": "更换前氧传感器",
        "solution_description": "更换信号漂移或失效的氧传感器，恢复空燃比闭环控制",
        "repair_method": "车辆熄火冷却后，断开氧传感器接插件，使用氧传感器专用套筒拆下旧传感器；按标准扭矩安装新传感器并恢复接插件；清除故障码后路试验证。",
        "parts": [
            {"part_name": "前氧传感器", "part_type": "oem", "price_estimate": "300 - 900 元", "source": "structured_repair_knowledge"},
        ],
        "labor": {"estimated_time": "0.5 - 1.0 小时", "source": "standard_repair_data", "source_confidence": "high"},
        "cost": {"parts_cost": "300 - 900 元", "labor_cost": "80 - 200 元", "total_cost": "380 - 1100 元", "currency": "CNY", "source": "case_work_order", "source_confidence": "medium"},
        "risk_level": "low",
        "warning_note": "氧传感器螺纹处可能烧结，拆卸需注意滑牙风险；安装时避免传感器探头接触油污。",
        "post_repair_validation": "清除故障码后路试，复扫确认故障码未复发，观察氧传感器电压在 0.1 - 0.9V 间正常波动。",
    },
    {
        "keywords": ["火花塞", "火花塞磨损"],
        "cause_id": "CAUSE_IGNITION_001",
        "solution_id": "RS_IGNITION_001",
        "solution_name": "更换火花塞",
        "solution_description": "按厂家规定型号与扭矩更换全部火花塞",
        "repair_method": "拆卸点火线圈，使用火花塞套筒逐一拆下旧火花塞；检查新火花塞间隙是否符合厂家标准；按规定扭矩安装并恢复点火线圈。",
        "parts": [
            {"part_name": "火花塞", "quantity": 4, "part_type": "oem", "price_estimate": "40 - 120 元/只", "source": "structured_repair_knowledge"},
        ],
        "labor": {"estimated_time": "0.5 - 1.0 小时", "source": "standard_repair_data", "source_confidence": "high"},
        "cost": {"parts_cost": "160 - 480 元", "labor_cost": "80 - 200 元", "total_cost": "240 - 680 元", "currency": "CNY", "source": "case_work_order", "source_confidence": "medium"},
        "risk_level": "low",
        "post_repair_validation": "清除故障码后路试，复扫确认失火类故障码未复发，观察各缸失火计数为 0。",
    },
    {
        "keywords": ["点火线圈"],
        "cause_id": "CAUSE_IGNITION_002",
        "solution_id": "RS_IGNITION_002",
        "solution_name": "更换点火线圈",
        "solution_description": "更换对调测试确认故障的点火线圈",
        "repair_method": "断开点火线圈接插件，拆下固定螺栓后取出故障线圈；安装新线圈并恢复接插件；清除故障码验证。",
        "parts": [
            {"part_name": "点火线圈", "part_type": "oem", "price_estimate": "150 - 500 元/只", "source": "structured_repair_knowledge"},
        ],
        "labor": {"estimated_time": "0.3 - 0.8 小时", "source": "standard_repair_data", "source_confidence": "high"},
        "cost": {"parts_cost": "150 - 500 元", "labor_cost": "50 - 160 元", "total_cost": "200 - 660 元", "currency": "CNY", "source": "case_work_order", "source_confidence": "medium"},
        "risk_level": "low",
        "post_repair_validation": "清除故障码后路试，复扫确认失火故障码未复发，对应气缸失火计数为 0。",
    },
    {
        "keywords": ["催化转换器效率下降", "催化转换器", "三元催化"],
        "cause_id": "CAUSE_EMISSION_001",
        "solution_id": "RS_EMISSION_001",
        "solution_name": "更换催化转换器",
        "solution_description": "更换效率低于阈值的催化转换器总成",
        "repair_method": "举升车辆，拆卸催化器前后法兰螺栓与氧传感器；取下旧催化器，更换新催化器总成并恢复氧传感器与法兰密封；清除故障码验证。",
        "parts": [
            {"part_name": "催化转换器总成", "part_type": "oem", "price_estimate": "2000 - 8000 元", "source": "structured_repair_knowledge"},
        ],
        "labor": {"estimated_time": "1.5 - 3.0 小时", "source": "standard_repair_data", "source_confidence": "medium"},
        "cost": {"parts_cost": "2000 - 8000 元", "labor_cost": "300 - 800 元", "total_cost": "2300 - 8800 元", "currency": "CNY", "source": "case_work_order", "source_confidence": "low"},
        "risk_level": "medium",
        "warning_note": "更换催化器成本较高，务必先排除氧传感器信号异常等误判因素；注意使用合规排放部件。",
        "post_repair_validation": "清除故障码后按 OBD 就绪工况行驶，复扫确认 P0420/P0430 未复发，后氧波形恢复平稳。",
    },
    {
        "keywords": ["节气门积碳", "节气门"],
        "cause_id": "CAUSE_SYM_001",
        "solution_id": "RS_SYM_001",
        "solution_name": "清洗节气门",
        "solution_description": "拆卸清洗节气门体积碳并完成怠速自学习",
        "repair_method": "拆卸进气管路露出节气门，使用节气门专用清洗剂清除积碳；恢复装配后按厂家流程执行怠速/节气门自学习。",
        "parts": [
            {"part_name": "节气门清洗剂", "part_type": "aftermarket", "price_estimate": "20 - 50 元", "source": "structured_repair_knowledge"},
        ],
        "labor": {"estimated_time": "0.5 - 1.0 小时", "source": "standard_repair_data", "source_confidence": "high"},
        "cost": {"parts_cost": "20 - 50 元", "labor_cost": "80 - 200 元", "total_cost": "100 - 250 元", "currency": "CNY", "source": "case_work_order", "source_confidence": "medium"},
        "risk_level": "low",
        "post_repair_validation": "清洗后路试确认怠速抖动消失，诊断仪读取节气门开度与怠速转速恢复正常范围。",
    },
]
