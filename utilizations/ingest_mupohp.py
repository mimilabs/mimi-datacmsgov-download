# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest the Medicare Outpatient files
# MAGIC
# MAGIC Three different levels of files exist:
# MAGIC
# MAGIC - provider-level (with a postfix, "_prvdr")
# MAGIC - geographic-level (with a postfix, "_geo")
# MAGIC

# COMMAND ----------

from pathlib import Path
import re
import csv
from pyspark.sql.types import IntegerType
from pyspark.sql.functions import col, lit, to_date, regexp_replace
from datetime import datetime
from dateutil.parser import parse
import pandas as pd

path = "/Volumes/mimi_ws_1/datacmsgov/src" # where all the input files are located
catalog = "mimi_ws_1" # delta table destination catalog
schema = "datacmsgov" # delta table destination schema
tablename = "mupohp" # destination table

# COMMAND ----------

def change_header(header_org):
    return [re.sub(r'\W+', '', column.lower().replace(' ','_'))
            for column in header_org]

# COMMAND ----------

# We want to skip those files that are already in the delta tables.
# We look up the table, and see if the files are already there or not.
files_exist = {}
writemode = "overwrite"
if spark.catalog.tableExists(f"{catalog}.{schema}.{tablename}"):
    files_exist = set([row["_input_file_date"] 
                   for row in 
                   (spark.read.table(f"{catalog}.{schema}.{tablename}")
                            .select("_input_file_date")
                            .distinct()
                            .collect())])
    writemode = "append"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Provider-Service-level (main)

# COMMAND ----------

files = []
for filepath in Path(f"{path}/{tablename}").glob("*_Prov_Svc*"):
    year = '20' + re.search("\_d[y]*(\d+)\_", filepath.stem.lower()).group(1)
    dt = parse(f"{year}-12-31").date()
    if dt not in files_exist:
        files.append((dt, filepath))
files = sorted(files, key=lambda x: x[0], reverse=True)

# COMMAND ----------

int_columns = {"bene_cnt", 
               "capc_srvcs",
               "outlier_srvcs"}
double_columns = {"avg_tot_sbmtd_chrgs", 
                  "avg_mdcr_alowd_amt",
                  "avg_mdcr_pymt_amt",
                  "avg_mdcr_stdzd_amt",
                  "avg_mdcr_outlier_amt"}
legacy_columns = {}

for item in files:
    # each file is relatively big
    # so we load the data using spark one by one just in case
    # the size hits a single machine memory
    df = (spark.read.format("csv")
            .option("header", "true")
            .load(str(item[1])))
    header = []
    for col_old, col_new_ in zip(df.columns, change_header(df.columns)):

        col_new = legacy_columns.get(col_new_, col_new_)
        header.append(col_new)
        
        if col_new in int_columns:
            df = df.withColumn(col_new, regexp_replace(col(col_old), "[\$,%]", "").cast("int"))
        elif col_new in double_columns:
            df = df.withColumn(col_new, regexp_replace(col(col_old), "[\$,%]", "").cast("double"))
        else:
            df = df.withColumn(col_new, col(col_old))
            
    df = (df.select(*header)
          .withColumn("_input_file_date", lit(item[0])))
    
    # These columns are added later
    # - rfrg_prvdr_last_name_org (used to be rfrg_prvdr_last_name)
    # - rfrg_prvdr_ruca_cat
    # - rfrg_prvdr_type_cd
    # Some of these are manually corrected above. However, just in case
    # we make the mergeSchema option "true"
    (df.write
        .format('delta')
        .mode(writemode)
        .option("mergeSchema", "true")
        .saveAsTable(f"{catalog}.{schema}.{tablename}"))
    
    writemode="append"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Geo-level (_geo)

# COMMAND ----------

tablename2 = f"{tablename}_geo"
files = []
files_exist = {}
writemode = "overwrite"

if spark.catalog.tableExists(f"{catalog}.{schema}.{tablename2}"):
    files_exist = set([row["_input_file_date"] 
                   for row in 
                   (spark.read.table(f"{catalog}.{schema}.{tablename2}")
                            .select("_input_file_date")
                            .distinct()
                            .collect())])
    writemode = "append"

for filepath in Path(f"{path}/{tablename}").glob("*_Geo*"):
    year = '20' + re.search("\_d[y]*(\d+)\_", filepath.stem.lower()).group(1)
    dt = parse(f"{year}-12-31").date()
    if dt not in files_exist:
        files.append((dt, filepath))

files = sorted(files, key=lambda x: x[0], reverse=True)

# COMMAND ----------

int_columns = {"bene_cnt",
               "capc_srvcs", 
               "outlier_srvcs"}
double_columns = {"avg_tot_sbmtd_chrgs",
                  "avg_mdcr_alowd_amt",
                  "avg_mdcr_pymt_amt",
                  "avg_mdcr_outlier_amt"}

for item in files:
    df = (spark.read.format("csv")
            .option("header", "true")
            .load(str(item[1])))
    header = []
    for col_old, col_new in zip(df.columns, change_header(df.columns)):
        header.append(col_new)
        if col_new in int_columns:
            df = df.withColumn(col_new, regexp_replace(col(col_old), "[\$,%]", "").cast("int"))
        elif col_new in double_columns:
            df = df.withColumn(col_new, regexp_replace(col(col_old), "[\$,%]", "").cast("double"))
        else:
            df = df.withColumn(col_new, col(col_old))
    df = (df.select(*header)
          .withColumn("_input_file_date", lit(item[0])))
    
    (df.write
        .format('delta')
        .mode(writemode)
        .option("mergeSchema", "true")
        .saveAsTable(f"{catalog}.{schema}.{tablename2}"))
    
    writemode="append"

# COMMAND ----------

