from fastapi import FastAPI, File, UploadFile, status
from fastapi.responses import JSONResponse
from google.cloud import storage
from dotenv import dotenv_values
from datetime import datetime
from pytz import timezone
import pandas as pd
import uvicorn

# Load .env
config = dotenv_values(".env")

app = FastAPI()

def response_template(status_code: int, error: bool, message: str, data: dict = None) -> JSONResponse:
    current_datetime = get_timestamp_now("%Y-%m-%d %H:%M:%S")
    response_value   = {
            "status_code" : status_code,
            "error"       : error,
            "message"     : message,
            "requested_at": current_datetime
            }
    if error == False:
        response_value.update({"data": data})
    return JSONResponse(status_code=status_code, content=response_value)

def get_timestamp_now(output_format: str) -> str:
    # Get current time with timezone UTC+7
    now_time     = datetime.now(timezone("Asia/Jakarta"))
    current_time = now_time.strftime(output_format)
    return current_time

def transform(file: File) -> pd.DataFrame:
    # Get current time with timezone UTC+7
    current_time = get_timestamp_now("%H%M%S")

    # Read input excel file
    df = pd.read_excel(file, dtype=str)
    
    # Read mapping file
    df_kodewilayah = pd.read_csv("source_map_kode_wilayah.csv", dtype=str, keep_default_na=False)

    # Transform actions
    df = df.drop(columns=["id_frm", "namaprovinsi","namakabupaten","namakecamatan","namakelurahan","koderw","namarw","kodert","namart","nama_istri","baduta","balita","pus_hamil","kesejahteraan_prioritas","sasaran_final"])
    df["nama_customer"] = df["nama_kepala_keluarga"]
    df["alamat_pemilik"] = df["alamat"]
    df["email"] = df["kode_keluarga"]
    df.rename(columns={"nama_kepala_keluarga":"nama_pemilik","nik":"nik_customer","kodeprovinsi":"kode_provinsi", "kodekabupaten":"kode_kota_kabupaten", "kodekecamatan":"kode_kecamatan", "kodekelurahan":"kode_kelurahan"}, inplace = True)
    new_df = df.merge(df_kodewilayah[["kode_provinsi","kode_kota_kabupaten","kode_kecamatan","kode_kelurahan","postal_code","kode_wilayah_concat"]], how="left", on=["kode_provinsi","kode_kota_kabupaten","kode_kecamatan","kode_kelurahan"])
    new_df = new_df.drop(columns=["kode_provinsi", "kode_kota_kabupaten", "kode_kecamatan", "kode_kelurahan"])
    new_df["tipe"],new_df["panjang"],new_df["lebar"],new_df["pembuatan_akun_user"],new_df["catatan_alamat"] = 1,1,1,"N",""
    new_df["email"]=  (new_df["email"].astype(str)).str.replace(r' ', '', regex=True)+ "@bgrtest.com"
    new_df.rename(columns={"kode_wilayah_concat":"kode_teritori","postal_code":"kode_pos_customer"}, inplace = True)
    new_df["telp_customer"] = new_df.apply(lambda row: "08{}{:>07d}".format(current_time,row.name), axis=1)
    new_df["telp_pemilik"] = new_df["telp_customer"]

    # Filter columns
    cols   = ["nama_customer","nik_customer","telp_customer","email","kode_pos_customer","alamat","catatan_alamat","tipe","panjang","lebar","nama_pemilik","telp_pemilik","alamat_pemilik","kode_teritori","pembuatan_akun_user"]
    new_df = new_df[cols]

    return new_df

def store_to_gcs(bucket: str, filename: str, dataframe: pd.DataFrame):
    # # For local development only
    # # Set the environment variable for authentication
    # service_account_path = '/app/credential.json'
    # os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = service_account_path

    # Create a storage client (using Application Default Credentials or a service account key)
    storage_client = storage.Client(project=config["project_id"])
    
    # Get a reference to the bucket
    bucket = storage_client.bucket(config["bucket_name"])

    # Create a blob object with the desired file path
    blob = bucket.blob(filename)
    
    # Write DataFrame to CSV directly to GCS using a StringIO buffer
    dataframe.to_excel(f"gs://{config['bucket_name']}/{filename}", index=False, engine="xlsxwriter")

    # Generate the public URL
    blob.make_public()
    public_url = blob.public_url

    return public_url

# Health check endpoint
@app.get("/healthcheck")
async def healthcheck():
    status_code = status.HTTP_200_OK
    return response_template(status_code=status_code, error=False, message="Service is healthy")

# Reformat endpoint
@app.post("/reformat")
async def upload_excel(file: UploadFile = File(...)):
    """Upload an Excel file and process its data."""

    # Validate file extension
    allowed_extensions = {"xlsx", "xls"}
    if file.filename.split(".")[-1].lower() not in allowed_extensions: 
        return response_template(status_code=status.HTTP_400_BAD_REQUEST, error=True, message="Invalid file extension")

    # Validate file size
    max_file_size = 5_000_000  # 5 MB
    if file.size > max_file_size: 
        return response_template(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, error=True, message="File size exceeds maximum limit (5 MB)")

    # Read and transform Excel file
    try:
        df = transform(file.file)
    except Exception as e:
        return response_template(status_code=status.HTTP_400_BAD_REQUEST, error=True, message=f"Failed to process Excel file. {e}")

    # Store result to GCS
    current_date_time = get_timestamp_now("%d%m%Y_%H%M%S")
    output_filename = f'{file.filename.split(".")[0].lower()}_{current_date_time}.xlsx'
    try:
        public_url = store_to_gcs(bucket=config["bucket_name"], filename=output_filename, dataframe=df)
    except Exception as e:
        return response_template(status_code=status.HTTP_400_BAD_REQUEST, error=True, message=f"File failed to be stored. {e}")
    else:
        if public_url:
            data = {
                "input_filename" : file.filename,
                "output_filename": output_filename,
                "row_count"      : len(df),
                "url_public"     : public_url
            }
        return response_template(status_code=status.HTTP_200_OK, error=False, message="File has been successfully reformated and stored", data=data)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)