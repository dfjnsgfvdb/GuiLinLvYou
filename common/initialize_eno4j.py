import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from py2neo import Graph, Node, Relationship
from datetime import datetime
from decimal import Decimal

"""
读取数据schema信息并初始化表关系
"""
# ==================== 配置 ====================
# MySQL 配置
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / f'.env.{os.getenv("ENV", "dev")}', override=False)

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "13006")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "1"),
    "database": os.getenv("MYSQL_DATABASE", "chat_db"),
    "charset": "utf8mb4",
}

# Neo4j 配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687").strip('"')
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j").strip('"')
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j123").strip('"')

# 批量提交大小
BATCH_SIZE = 1000


# ==============================================


def connect_mysql():
    return pymysql.connect(**MYSQL_CONFIG)


def connect_neo4j():
    graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return graph


def convert_value(value):
    """转换可能不被py2neo支持的数据类型"""
    if isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, Decimal):
        return float(value)
    else:
        return value


def get_tables_from_database(connection):
    """从MySQL数据库中自动获取表结构信息"""
    tables = {}

    with connection.cursor() as cursor:
        # 获取所有表名
        cursor.execute("SHOW TABLES")
        table_names = [row[0] for row in cursor.fetchall()]

        # 获取每个表的列信息
        for table_name in table_names:
            cursor.execute(f"SHOW COLUMNS FROM {table_name}")
            columns = cursor.fetchall()

            # 处理列信息，标记主键和外键
            fields = []
            for column in columns:
                field = column[0]  # 字段名
                key = column[3]  # 键信息 (PRI表示主键, MUL表示外键等)

                if key == "PRI":
                    fields.append(f"{field} [主键]")
                elif key == "MUL":
                    fields.append(f"{field} [外键]")
                else:
                    fields.append(field)

            tables[table_name] = {"name": table_name, "fields": fields}

    return tables


# 表之间的关系 手动维护
RELATIONSHIPS = [
    {
        "from_table": "t_customers",
        "to_table": "t_sales_orders",
        "description": "t_customers places t_sales_orders",
        "field_relation": "customer_id references customer_id",
    },
    {
        "from_table": "t_sales_orders",
        "to_table": "t_order_details",
        "description": "t_sales_orders contains t_order_details",
        "field_relation": "order_id references order_id",
    },
    {
        "from_table": "t_products",
        "to_table": "t_order_details",
        "description": "t_products belongs to t_order_details",
        "field_relation": "product_id references product_id",
    },
    {
        "from_table": "t_user",
        "to_table": "t_user_qa_record",
        "description": "t_user belongs to t_user_qa_record",
        "field_relation": "id references user_id",
    },
]


# ------------------- 写入 Neo4j 的函数 -------------------
def create_constraints(graph):
    # 为节点创建唯一性约束
    graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (t:Table) REQUIRE t.name IS UNIQUE")
    print("Constraints created.")


def create_table_nodes(graph, tables):
    """创建表示表结构的节点"""
    for table_name, table_info in tables.items():
        # 创建表节点
        graph.run(
            "MERGE (t:Table {name: $name}) " "SET t.label = $label, " "    t.fields = $fields",
            name=table_info["name"],
            label=table_name,
            fields=table_info["fields"],
        )

    print("Table nodes created.")


def create_table_relationships(graph):
    """创建表之间的关系"""
    for rel in RELATIONSHIPS:
        graph.run(
            "MATCH (from_table:Table {label: $from_table}) "
            "MATCH (to_table:Table {label: $to_table}) "
            "MERGE (from_table)-[r:REFERENCES {description: $description, field_relation: $field_relation}]->(to_table)",
            from_table=rel["from_table"],
            to_table=rel["to_table"],
            description=rel["description"],
            field_relation=rel["field_relation"],
        )

    print("Table relationships created.")


# ------------------- 主函数 -------------------
def main():
    print("Starting table relationship graph initialization...")

    # 连接数据库
    mysql_conn = connect_mysql()
    neo4j_graph = connect_neo4j()

    try:
        # 从数据库中获取表结构信息
        tables = get_tables_from_database(mysql_conn)

        # 清空现有数据
        print("Clearing existing Neo4j data...")
        neo4j_graph.delete_all()

        # 创建约束
        create_constraints(neo4j_graph)

        # 创建表节点
        print("Creating table nodes...")
        create_table_nodes(neo4j_graph, tables)

        # 创建表关系
        print("Creating table relationships...")
        create_table_relationships(neo4j_graph)

        print("Table relationship graph initialization completed.")

    except Exception as e:
        print("Error:", str(e))
        raise
    finally:
        mysql_conn.close()


if __name__ == "__main__":
    main()
