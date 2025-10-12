"""
SQLite 宏观数据存储实现（MySQL 降级方案）
"""

import pandas as pd
import sqlite3
import os
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from .base import MacroDataStorage, INDICATOR_TABLE_MAPPING, INDICATOR_TIME_FIELD

logger = logging.getLogger(__name__)


class SQLiteMacroStorage(MacroDataStorage):
    """SQLite 宏观数据存储实现"""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.db_path = (
            config.get("db_path", "data/macro/macro_data.db")
            if config
            else "data/macro/macro_data.db"
        )
        self.connection = None

    def connect(self) -> bool:
        """连接 SQLite"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row  # 使返回结果可以按列名访问

            # 创建表结构
            self._create_tables()

            self._connected = True
            logger.info(f"✅ SQLite 宏观数据存储连接成功: {self.db_path}")
            return True

        except Exception as e:
            logger.error(f"❌ SQLite 宏观数据存储连接失败: {e}")
            self._connected = False
            return False

    def _create_tables(self):
        """创建SQLite表结构（基于MySQL结构简化）"""
        try:
            cursor = self.connection.cursor()

            # GDP 表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS cn_gdp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL UNIQUE,
                gdp REAL,
                gdp_yoy REAL,
                pi REAL,
                pi_yoy REAL,
                si REAL,
                si_yoy REAL,
                ti REAL,
                ti_yoy REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            # CPI 表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS cn_cpi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                time DATETIME NOT NULL,
                nt_val REAL,
                nt_yoy REAL,
                nt_mom REAL,
                nt_accu REAL,
                town_val REAL,
                town_yoy REAL,
                town_mom REAL,
                town_accu REAL,
                cnt_val REAL,
                cnt_yoy REAL,
                cnt_mom REAL,
                cnt_accu REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            # PPI 表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS cn_ppi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                time DATETIME NOT NULL,
                ppi_yoy REAL,
                ppi_mp_yoy REAL,
                ppi_mp_qm_yoy REAL,
                ppi_mp_rm_yoy REAL,
                ppi_mp_p_yoy REAL,
                ppi_cg_yoy REAL,
                ppi_cg_f_yoy REAL,
                ppi_cg_c_yoy REAL,
                ppi_cg_adu_yoy REAL,
                ppi_cg_dcg_yoy REAL,
                ppi_mom REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            # 货币供应量表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS cn_money_supply (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                time DATETIME NOT NULL,
                m0 REAL,
                m0_yoy REAL,
                m0_mom REAL,
                m1 REAL,
                m1_yoy REAL,
                m1_mom REAL,
                m2 REAL,
                m2_yoy REAL,
                m2_mom REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            # 社融表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS cn_social_financing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                time DATETIME NOT NULL,
                inc_month REAL,
                inc_cumval REAL,
                stk_endval REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            # PMI 表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS cn_pmi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                time DATETIME NOT NULL,
                pmi010000 REAL,
                pmi010100 REAL,
                pmi010200 REAL,
                pmi010300 REAL,
                pmi010400 REAL,
                pmi020100 REAL,
                pmi030000 REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            # LPR 表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS cn_lpr (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                time DATETIME NOT NULL,
                "1y" REAL,
                "5y" REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            self.connection.commit()
            logger.info("✅ SQLite 表结构创建完成")

        except Exception as e:
            logger.error(f"❌ 创建 SQLite 表结构失败: {e}")
            raise

    def is_available(self) -> bool:
        """检查 SQLite 是否可用"""
        return self._connected and self.connection is not None

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

            cursor = self.connection.cursor()
            query = f"SELECT MAX({time_field}) as latest_period FROM {table_name}"
            result = cursor.execute(query).fetchone()

            if result and result["latest_period"]:
                return str(result["latest_period"])
            return None

        except Exception as e:
            logger.error(f"❌ 获取{indicator}最新时期失败: {e}")
            return None

    def save_data(self, indicator: str, data: pd.DataFrame) -> bool:
        """保存数据到 SQLite"""
        if not self.is_available() or data.empty:
            return False

        try:
            table_name = INDICATOR_TABLE_MAPPING.get(indicator)
            if not table_name:
                logger.error(f"❌ 未知指标: {indicator}")
                return False

            # 使用 pandas to_sql 保存数据
            data.to_sql(table_name, self.connection, if_exists="replace", index=False)

            logger.info(f"✅ 保存{indicator}数据成功: {len(data)}条记录")
            return True

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

            # 构建查询条件
            where_conditions = []
            if start_period:
                where_conditions.append(f"{time_field} >= '{start_period}'")
            if end_period:
                where_conditions.append(f"{time_field} <= '{end_period}'")

            where_clause = (
                f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
            )

            query = f"SELECT * FROM {table_name}{where_clause} ORDER BY {time_field}"

            df = pd.read_sql_query(query, self.connection)

            logger.info(f"✅ 获取{indicator}数据成功: {len(df)}条记录")
            return df

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

            query = f"""
            SELECT * FROM {table_name}
            ORDER BY {time_field} DESC
            LIMIT {periods}
            """

            df = pd.read_sql_query(query, self.connection)

            if not df.empty:
                # 重新按时间正序排序
                df = df.sort_values(time_field).reset_index(drop=True)

            logger.info(f"✅ 获取{indicator}最近{periods}期数据成功: {len(df)}条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取{indicator}最近{periods}期数据失败: {e}")
            return pd.DataFrame()

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

            cursor = self.connection.cursor()

            if period:
                query = f"DELETE FROM {table_name} WHERE {time_field} = ?"
                cursor.execute(query, (period,))
                message = f"删除{indicator}数据 (时期: {period})"
            else:
                query = f"DELETE FROM {table_name}"
                cursor.execute(query)
                message = f"清空{indicator}所有数据"

            self.connection.commit()
            logger.info(f"✅ {message}成功")
            return True

        except Exception as e:
            logger.error(f"❌ 删除{indicator}数据失败: {e}")
            return False

    def close(self):
        """关闭连接"""
        if self.connection:
            self.connection.close()
            self._connected = False
            logger.info("✅ SQLite 连接已关闭")
