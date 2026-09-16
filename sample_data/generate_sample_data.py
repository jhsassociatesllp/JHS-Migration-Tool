"""
Generates sample CSV datasets for manual testing and demos:

1. customer_master.csv / customer.csv — the small example from the spec
   (OBCustomerNo/custid, 1003 missing, 1004 extra).
2. large_source.csv / large_target.csv — a 1,000,000+ row synthetic
   dataset with a realistic mix of missing/extra/changed/duplicate
   records, for benchmarking the engine's large-file performance.

Usage:
    python3 sample_data/generate_sample_data.py
"""
import os
import duckdb

OUT_DIR = os.path.dirname(__file__)


def generate_small_example():
    with open(os.path.join(OUT_DIR, "customer_master.csv"), "w") as f:
        f.write("OBCustomerNo,FirstName,LastName,DOB,Mobile,Email\n")
        f.write("1001,Rahul,Sharma,12-04-1995,9876543210,rahul@example.com\n")
        f.write("1002,Anita,Verma,03-11-1988,9876500000,anita@example.com\n")
        f.write("1003,Suresh,Iyer,25-01-1990,9876511111,suresh@example.com\n")

    with open(os.path.join(OUT_DIR, "customer.csv"), "w") as f:
        f.write("custid,first_name,last_name,date_of_birth,phone,email\n")
        f.write("1001,Rahul,Sharma,1995-04-12,9876543210,rahul@example.com\n")
        f.write("1002,Anita,Verma,1988-11-03,9876500000,changed_anita@example.com\n")
        f.write("1004,John,Doe,1992-07-19,9876522222,john@example.com\n")
    print("Wrote customer_master.csv and customer.csv (small spec example).")


def generate_large_dataset(source_rows: int = 1_200_000, target_rows: int = 1_180_000):
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")

    src_path = os.path.join(OUT_DIR, "large_source.csv")
    tgt_path = os.path.join(OUT_DIR, "large_target.csv")

    # Source: sequential IDs, some with leading-zero formatted duplicates injected.
    con.execute(f"""
        COPY (
            SELECT
                i AS OBCustomerNo,
                'FirstName' || i AS FirstName,
                'LastName' || (i % 5000) AS LastName,
                strftime(DATE '1970-01-01' + INTERVAL (i % 18000) DAY, '%d/%m/%Y') AS DOB,
                'user' || i || '@example.com' AS Email
            FROM range(1, {source_rows + 1}) t(i)
        ) TO '{src_path}' (HEADER, DELIMITER ',')
    """)

    # Target: ~98% overlap with source, some changed emails, some extra new ids,
    # and roughly 1.5% of source ids intentionally dropped (missing in target).
    con.execute(f"""
        COPY (
            SELECT
                i AS custid,
                'FirstName' || i AS first_name,
                'LastName' || (i % 5000) AS last_name,
                CAST(DATE '1970-01-01' + INTERVAL (i % 18000) DAY AS VARCHAR) AS date_of_birth,
                CASE WHEN i % 400 = 0 THEN 'updated' || i || '@example.com' ELSE 'user' || i || '@example.com' END AS email
            FROM range(1, {target_rows + 1}) t(i)
            WHERE i % 67 != 0
            UNION ALL
            SELECT
                i AS custid,
                'NewFirstName' || i AS first_name,
                'NewLastName' || (i % 5000) AS last_name,
                CAST(DATE '1970-01-01' + INTERVAL (i % 18000) DAY AS VARCHAR) AS date_of_birth,
                'newuser' || i || '@example.com' AS email
            FROM range({target_rows + 1}, {target_rows + 1 + 20000}) t(i)
        ) TO '{tgt_path}' (HEADER, DELIMITER ',')
    """)
    con.close()
    print(f"Wrote large_source.csv (~{source_rows:,} rows) and large_target.csv for performance benchmarking.")


if __name__ == "__main__":
    generate_small_example()
    generate_large_dataset()
