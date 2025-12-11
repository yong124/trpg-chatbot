import os
from dotenv import load_dotenv
import google.generativeai as genai

# .env 파일에서 환경 변수 로드
load_dotenv(dotenv_path='backend/api_key.env')

# Gemini API 키 설정
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")

genai.configure(api_key=GEMINI_API_KEY)

print("사용 가능한 Gemini 모델 목록 ('generateContent' 지원):")
for m in genai.list_models():
  if 'generateContent' in m.supported_generation_methods:
    print(m.name)
