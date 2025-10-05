#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用API响应封装器
提供统一的API返回格式，与Java客户端ExternalApiManagerClient兼容

响应格式:
{
    "status": "success" | "error" | "warning",
    "message": "操作描述信息",
    "data": {...} | [...] | null
}
"""

from typing import Any, Optional, Dict
from enum import Enum


class ResponseStatus(Enum):
    """响应状态枚举"""

    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"


class APIResponse:
    """API响应封装类"""

    @staticmethod
    def success(data: Any = None, message: str = "操作成功") -> Dict[str, Any]:
        """
        成功响应

        Args:
            data: 响应数据
            message: 成功消息

        Returns:
            Dict: 统一格式的成功响应
        """
        return {
            "status": ResponseStatus.SUCCESS.value,
            "message": message,
            "data": data,
        }

    @staticmethod
    def error(
        message: str = "操作失败",
        error_code: Optional[str] = None,
        details: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        错误响应

        Args:
            message: 错误消息
            error_code: 错误代码(可选)
            details: 错误详情(可选)

        Returns:
            Dict: 统一格式的错误响应
        """
        response = {
            "status": ResponseStatus.ERROR.value,
            "message": message,
            "data": None,
        }

        if error_code:
            response["error_code"] = error_code

        if details:
            response["details"] = details

        return response

    @staticmethod
    def warning(data: Any = None, message: str = "操作完成但有警告") -> Dict[str, Any]:
        """
        警告响应

        Args:
            data: 响应数据
            message: 警告消息

        Returns:
            Dict: 统一格式的警告响应
        """
        return {
            "status": ResponseStatus.WARNING.value,
            "message": message,
            "data": data,
        }


# 便捷函数
def success_response(data: Any = None, message: str = "操作成功") -> Dict[str, Any]:
    """快捷成功响应函数"""
    return APIResponse.success(data, message)


def error_response(
    message: str = "操作失败",
    error_code: Optional[str] = None,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    """快捷错误响应函数"""
    return APIResponse.error(message, error_code, details)


def warning_response(
    data: Any = None, message: str = "操作完成但有警告"
) -> Dict[str, Any]:
    """快捷警告响应函数"""
    return APIResponse.warning(data, message)
