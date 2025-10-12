"""
MySQL 宏观数据存储实现
"""

import pandas as pd
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from .base import MacroDataStorage, INDICATOR_TABLE_MAPPING, INDICATOR_TIME_FIELD
from ....core.connection_registry import get_connection_registry

logger = logging.getLogger(__name__)


class MySQLMacroStorage(MacroDataStorage):
    """MySQL 宏观数据存储实现"""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.connection_registry = get_connection_registry()

    def connect(self) -> bool:
        """连接 MySQL"""
        try:
            mysql_conn = self.connection_registry.get_mysql()
            if mysql_conn and mysql_conn.is_healthy():
                self._connected = True
                logger.info("✅ MySQL 宏观数据存储连接成功")
                return True
            else:
                logger.warning("⚠️ MySQL 连接不健康")
                return False
        except Exception as e:
            logger.error(f"❌ MySQL 宏观数据存储连接失败: {e}")
            self._connected = False
            return False

    def is_available(self) -> bool:
        """检查 MySQL 是否可用"""
        try:
            mysql_conn = self.connection_registry.get_mysql()
            return mysql_conn and mysql_conn.is_healthy()
        except:
            return False

    def get_latest_period(self, indicator: str) -> Optional[str]:
        """获取指定指标的最新数据时期"""
        if not self.is_available():
            return None

        try:
            table_name = INDICATOR_TABLE_MAPPING.get(indicator)
            time_field = INDICATOR_TIME_FIELD.get(indicator)

            if not table_name or not time_field:
                logger.error(f"❌ 未知指标: {indicator}")
                return None

            mysql_conn = self.connection_registry.get_mysql()

            query = f"""
            SELECT MAX({time_field}) as latest_period 
            FROM {table_name}
            """

            result = mysql_conn.execute_query(query)

            if result and len(result) > 0 and result[0]["latest_period"]:
                return str(result[0]["latest_period"])
            return None

        except Exception as e:
            logger.error(f"❌ 获取{indicator}最新时期失败: {e}")
            return None

    def save_data(self, indicator: str, data: pd.DataFrame) -> bool:
        """保存数据到 MySQL"""
        if not self.is_available() or data.empty:
            return False

        try:
            table_name = INDICATOR_TABLE_MAPPING.get(indicator)
            if not table_name:
                logger.error(f"❌ 未知指标: {indicator}")
                return False

            mysql_conn = self.connection_registry.get_mysql()

            # 使用 pandas to_sql 保存数据
            success = mysql_conn.save_dataframe(data, table_name, if_exists="replace")

            if success:
                logger.info(f"✅ 保存{indicator}数据成功: {len(data)}条记录")
                return True
            else:
                logger.error(f"❌ 保存{indicator}数据失败")
                return False

        except Exception as e:
            logger.error(f"❌ 保存{indicator}数据异常: {e}")
            return False

    def get_data(
        self, indicator: str, start_period: str = None, end_period: str = None
    ) -> pd.DataFrame:
        """获取指定时间范围的数据"""
        if not self.is_available():
            return pd.DataFrame()

        try:
            table_name = INDICATOR_TABLE_MAPPING.get(indicator)
            time_field = INDICATOR_TIME_FIELD.get(indicator)

            if not table_name or not time_field:
                logger.error(f"❌ 未知指标: {indicator}")
                return pd.DataFrame()

            mysql_conn = self.connection_registry.get_mysql()

            # 构建查询条件
            where_conditions = []
            if start_period:
                where_conditions.append(f"{time_field} >= '{start_period}'")
            if end_period:
                where_conditions.append(f"{time_field} <= '{end_period}'")

            where_clause = (
                f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
            )

            query = f"""
            SELECT * FROM {table_name}
            {where_clause}
            ORDER BY {time_field}
            """

            result = mysql_conn.execute_query(query)

            if result:
                df = pd.DataFrame(result)
                logger.info(f"✅ 获取{indicator}数据成功: {len(df)}条记录")
                return df
            else:
                logger.warning(f"⚠️ {indicator}数据为空")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ 获取{indicator}数据失败: {e}")
            return pd.DataFrame()

    def get_recent_data(self, indicator: str, periods: int) -> pd.DataFrame:
        """获取最近N期数据"""
        if not self.is_available():
            return pd.DataFrame()

        try:
            table_name = INDICATOR_TABLE_MAPPING.get(indicator)
            time_field = INDICATOR_TIME_FIELD.get(indicator)

            if not table_name or not time_field:
                logger.error(f"❌ 未知指标: {indicator}")
                return pd.DataFrame()

            mysql_conn = self.connection_registry.get_mysql()

            query = f"""
            SELECT * FROM {table_name}
            ORDER BY {time_field} DESC
            LIMIT {periods}
            """

            result = mysql_conn.execute_query(query)

            if result:
                df = pd.DataFrame(result)
                # 重新按时间正序排序
                df = df.sort_values(time_field).reset_index(drop=True)
                logger.info(
                    f"✅ 获取{indicator}最近{periods}期数据成功: {len(df)}条记录"
                )
                return df
            else:
                logger.warning(f"⚠️ {indicator}最近{periods}期数据为空")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ 获取{indicator}最近{periods}期数据失败: {e}")
            return pd.DataFrame()

    def get_latest_data(self, indicator: str, periods: int = 1000) -> pd.DataFrame:
        """
        获取指标的最新数据（用于缺失数据检测）

        Args:
            indicator: 指标名称
            periods: 获取的最大期数（默认1000，用于检测）

        Returns:
            指标的所有或最新数据
        """
        return self.get_recent_data(indicator, periods)

    def delete_data(self, indicator: str, period: str = None) -> bool:
        """删除数据"""
        if not self.is_available():
            return False

        try:
            table_name = INDICATOR_TABLE_MAPPING.get(indicator)
            time_field = INDICATOR_TIME_FIELD.get(indicator)

            if not table_name or not time_field:
                logger.error(f"❌ 未知指标: {indicator}")
                return False

            mysql_conn = self.connection_registry.get_mysql()

            if period:
                query = f"DELETE FROM {table_name} WHERE {time_field} = '{period}'"
                message = f"删除{indicator}数据 (时期: {period})"
            else:
                query = f"DELETE FROM {table_name}"
                message = f"清空{indicator}所有数据"

            mysql_conn.execute_query(query)
            logger.info(f"✅ {message}成功")
            return True

        except Exception as e:
            logger.error(f"❌ 删除{indicator}数据失败: {e}")
            return False
