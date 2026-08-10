"""中台统一异常定义。"""


class ToolPlatformError(Exception):
    """中台基础异常。"""

    def __init__(self, message: str, code: int = 50000):
        self.message = message
        self.code = code
        super().__init__(message)


class ToolNotFoundError(ToolPlatformError):
    def __init__(self, tool_name: str):
        super().__init__(f"工具不存在: {tool_name}", code=40400)


class ToolInputValidationError(ToolPlatformError):
    def __init__(self, tool_name: str, detail: str):
        super().__init__(f"工具 {tool_name} 入参校验失败: {detail}", code=40000)


class ToolOutputValidationError(ToolPlatformError):
    def __init__(self, tool_name: str, detail: str):
        super().__init__(f"工具 {tool_name} 出参校验失败: {detail}", code=50001)


class ToolExecutionError(ToolPlatformError):
    def __init__(self, tool_name: str, detail: str):
        super().__init__(f"工具 {tool_name} 执行失败: {detail}", code=50002)
