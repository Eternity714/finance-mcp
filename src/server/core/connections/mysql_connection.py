"""
MySQL 数据源连接管理
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging

try:
    import pymysql
    from pymysql.cursors import DictCursor
    from dbutils.pooled_db import PooledDB
except ImportError:
    pymysql = None
    DictCursor = None
    PooledDB = None

from .base import DataSourceConnection

logger = logging.getLogger(__name__)


class MySQLConnection(DataSourceConnection):
    """MySQL 数据源连接（连接池）"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 MySQL 连接池

        Args:
            config: 配置字典，需包含:
                - host: MySQL 主机
                - port: MySQL 端口
                - user: 用户名
                - password: 密码
                - database: 数据库名
                - pool_size: 连接池大小（可选，默认10）
                - charset: 字符集（可选，默认utf8mb4）
        """
        super().__init__(config)

        self.host = config.get("host", "localhost")
        self.port = config.get("port", 3306)
        self.user = config.get("user", "root")
        self.password = config.get("password", "")
        self.database = config.get("database")
        self.pool_size = config.get("pool_size", 10)
        self.charset = config.get("charset", "utf8mb4")

        if not self.database:
            logger.error("❌ MySQL database 未配置")
            raise ValueError("MySQL database 未配置")

        if pymysql is None or PooledDB is None:
            logger.error("❌ pymysql 或 DBUtils 未安装")
            raise ImportError(
                "pymysql 或 DBUtils 未安装，请执行: pip install pymysql DBUtils"
            )

    def connect(self) -> bool:
        """建立 MySQL 连接池"""
        try:
            logger.info(
                f"🔄 正在连接 MySQL: {self.user}@{self.host}:{self.port}/{self.database}"
            )

            # 创建连接池
            self._client = PooledDB(
                creator=pymysql,
                maxconnections=self.pool_size,
                mincached=2,
                maxcached=5,
                blocking=True,
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=DictCursor,
            )

            # 测试连接
            if self.is_healthy():
                self._connected = True
                self._connection_time = datetime.now()
                self.reset_error()
                logger.info(f"✅ MySQL 连接池创建成功 (池大小: {self.pool_size})")
                return True
            else:
                logger.error("❌ MySQL 健康检查失败")
                return False

        except Exception as e:
            logger.error(f"❌ MySQL 连接失败: {e}")
            self._connected = False
            self.increment_error()
            return False

    def disconnect(self) -> bool:
        """关闭 MySQL 连接池"""
        try:
            if self._client:
                # PooledDB 没有显式的 close 方法，Python GC 会自动处理
                self._client = None
                self._connected = False
                logger.info("✅ MySQL 连接池已关闭")
            return True
        except Exception as e:
            logger.error(f"❌ MySQL 关闭失败: {e}")
            return False

    def is_healthy(self) -> bool:
        """
        健康检查

        通过执行简单的 SELECT 1 测试连接是否正常
        """
        if not self._client:
            return False

        connection = None
        try:
            # 从连接池获取连接
            connection = self._client.connection()
            cursor = connection.cursor()

            # 执行测试查询
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            cursor.close()

            if result:
                self.reset_error()
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"❌ MySQL 健康检查失败: {e}")
            self.increment_error()
            return False
        finally:
            if connection:
                connection.close()

    def get_client(self) -> PooledDB:
        """
        获取 MySQL 连接池

        Returns:
            PooledDB: MySQL 连接池实例
        """
        return super().get_client()

    def get_connection(self):
        """
        从连接池获取一个连接

        Returns:
            pymysql.Connection: MySQL 连接
        """
        if not self._client:
            raise ConnectionError("MySQL 连接池未初始化")

        return self._client.connection()

    def execute_query(self, sql: str, params: Optional[tuple] = None) -> list:
        """
        执行查询并返回结果

        Args:
            sql: SQL 查询语句
            params: 查询参数

        Returns:
            list: 查询结果列表
        """
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute(sql, params)
            result = cursor.fetchall()

            cursor.close()
            return result

        except Exception as e:
            logger.error(f"❌ 执行查询失败: {e}\nSQL: {sql}")
            raise
        finally:
            if connection:
                connection.close()

    def execute_update(self, sql: str, params: Optional[tuple] = None) -> int:
        """
        执行更新操作（INSERT/UPDATE/DELETE）

        Args:
            sql: SQL 语句
            params: 参数

        Returns:
            int: 受影响的行数
        """
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            affected_rows = cursor.execute(sql, params)
            connection.commit()

            cursor.close()
            return affected_rows

        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"❌ 执行更新失败: {e}\nSQL: {sql}")
            raise
        finally:
            if connection:
                connection.close()

    def save_dataframe(self, df, table_name: str, if_exists: str = "replace") -> bool:
        """
        保存 DataFrame 到 MySQL 表

        Args:
            df: 要保存的 DataFrame
            table_name: 表名
            if_exists: 如果表存在的处理方式 ('replace', 'append', 'fail')

        Returns:
            bool: 是否保存成功
        """
        try:
            if df.empty:
                logger.warning(f"⚠️ DataFrame 为空，跳过保存到 {table_name}")
                return True

            # 如果是 replace 模式，先清空表
            if if_exists == "replace":
                self.execute_update(f"DELETE FROM {table_name}")

            # 批量插入数据
            columns = list(df.columns)
            placeholders = ", ".join(["%s"] * len(columns))
            columns_str = ", ".join(columns)

            insert_sql = (
                f"INSERT INTO {table_name} ({columns_str}) " f"VALUES ({placeholders})"
            )

            # 转换 DataFrame 为数据列表
            data_list = []
            for _, row in df.iterrows():
                data_list.append(tuple(row.values))

            # 批量插入
            self._batch_insert(insert_sql, data_list)

            logger.info(f"✅ DataFrame 保存到 {table_name} 成功: {len(df)} 条记录")
            return True

        except Exception as e:
            logger.error(f"❌ DataFrame 保存到 {table_name} 失败: {e}")
            return False

    def _batch_insert(self, sql: str, data_list: list):
        """批量插入数据"""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            # 批量插入
            cursor.executemany(sql, data_list)
            connection.commit()

            cursor.close()

        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"❌ 批量插入失败: {e}")
            raise
        finally:
            if connection:
                connection.close()
