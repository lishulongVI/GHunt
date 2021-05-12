import uvicorn
from fastapi import FastAPI
from modules.email_json import email_hunt
import json

app = FastAPI()


@app.get("/{email}/{services}")
async def read_root(email, services):
    try:
        return json.loads(json.dumps(email_hunt(email, services), default=str))
    except Exception as e:
        return {'error': str(e)}


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=3601, workers=4)
