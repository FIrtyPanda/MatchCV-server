from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pathlib import Path
import tempfile, uuid, os, json
import traceback
import shutil
from databases.models import User, CVUpload, ChatHistory
from databases.database import get_db
from nlp.cv_processor import extract_text_from_pdf, clean_text, extract_keywords, detect_language
import google.generativeai as genai

router = APIRouter()

# === Fungsi Gemini ===
def ask_gemini(keywords: list[str]) -> str:
    keyword_summary = "\n".join([f"- {kw}" for kw in keywords])

    prompt = (
        f"Berikut ini adalah ringkasan keterampilan, pengalaman, dan latar belakang pengguna:\n\n"
        f"{keyword_summary}\n\n"
        f"Tugas Anda:\n"
        f"1. Bayangkan Anda adalah seorang career coach profesional.\n"
        f"2. Rekomendasikan **5 pekerjaan** yang paling sesuai dengan profil pengguna di atas.\n"
        f"3. Untuk setiap pekerjaan yang Anda rekomendasikan:\n"
        f"   - Berikan **nama posisi** yang spesifik dan umum dikenal.\n"
        f"   - Jelaskan **mengapa pengguna cocok** untuk posisi tersebut berdasarkan profil.\n"
        f"   - **Jangan menyebut kata 'keyword'** dan **hindari mengutip frasa dari daftar di atas secara persis**.\n"
        f"   - Parafrase informasi agar terdengar alami dan profesional.\n"
        f"4. **Gunakan format Markdown yang rapi**:\n"
        f"   - Gunakan heading dengan `##` untuk nama pekerjaan.\n"
        f"   - Pisahkan **setiap heading** dengan **satu baris kosong di atas dan bawah**.\n"
        f"   - Gunakan bullet list (`-`) atau numbered list (`1.`) dengan **satu baris kosong sebelum list**.\n"
        f"   - Gunakan `**bold**` jika ingin menyorot istilah penting atau nama proyek.\n"
        f"   - Pisahkan paragraf dengan satu baris kosong.\n"
        f"5. Hindari jawaban yang terlalu umum. Buat jawaban terasa personal dan kontekstual.\n\n"
        f"Tambahkan kalimat pembuka berikut sebelum daftar pekerjaan:\n"
        f"`## **Berikut adalah 5 rekomendasi pekerjaan yang paling sesuai dengan profil pengguna, beserta alasannya:**`\n"
    )

    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error from Gemini: {str(e)}"

# === Upload CV Endpoint ===
@router.post("/upload")
async def upload_cv(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File harus berformat PDF.")

    try:
        tmp_path = Path(tempfile.gettempdir()) / f"{uuid.uuid4()}.pdf"
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        raw_text = extract_text_from_pdf(str(tmp_path)).replace('\x00', '')
        cleaned = clean_text(raw_text)
        lang_code = detect_language(cleaned)
        lang = "English" if lang_code == "en" else "Non-English"
        keywords = extract_keywords(cleaned, language=lang_code, top_n=25)

        user = request.session.get("user") if hasattr(request, "session") else None

        # === Jika keyword terlalu sedikit, tetap kirim ke Gemini ===
        if not keywords or len(keywords) < 5:
            fallback_prompt = (
                "Balas pengguna dengan **tepat sesuai isi berikut**. Jangan tambahkan atau ubah apapun:\n\n"
                "Saya mencoba membaca file yang Anda unggah, namun tidak berhasil menemukan informasi khas dari sebuah CV "
                "seperti pengalaman kerja, pendidikan, atau keahlian. "
                "Mohon pastikan bahwa file yang Anda unggah memang merupakan CV (Curriculum Vitae) yang valid.\n\n"
                "Jika Anda membutuhkan bantuan cara membuat CV, saya siap membantu!"
            )

            model = genai.GenerativeModel("models/gemini-2.0-flash")
            response = model.generate_content(fallback_prompt)

            os.remove(tmp_path)

            return JSONResponse({
                "language": lang,
                "keywords": [],
                "raw_gemini_response": response.text,
                "saved": False,
                "upload_id": None
            })

        raw_response = ask_gemini(keywords)
        saved = False

        if user:
            os.makedirs("cv_uploads", exist_ok=True)
            saved_path = f"cv_uploads/{uuid.uuid4()}.pdf"
            shutil.copy(str(tmp_path), saved_path)
            os.remove(tmp_path)

            cv_record = CVUpload(
                user_id=user["id"],
                original_filename=file.filename,
                saved_path=saved_path,
                extracted_text=raw_text,
                keywords=json.dumps(keywords),
            )
            db.add(cv_record)
            db.commit()
            db.refresh(cv_record)

            db.add_all([
                ChatHistory(
                    user_id=user["id"],
                    cv_upload_id=cv_record.id,
                    role="user",
                    message="Berikut CV saya. Mohon rekomendasi pekerjaan."
                ),
                ChatHistory(
                    user_id=user["id"],
                    cv_upload_id=cv_record.id,
                    role="llm",
                    message=raw_response
                )
            ])
            db.commit()

            saved = True
        else:
            os.remove(tmp_path)

        return JSONResponse({
            "language": lang,
            "keywords": keywords,
            "raw_gemini_response": raw_response,
            "saved": saved,
            "upload_id": cv_record.id if saved else None
        })

    except Exception as e:
        print("[UPLOAD ERROR]")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error: " + str(e))

# === Ambil Riwayat Upload User ===
@router.get("/my-uploads")
def get_my_uploads(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(status_code=401, detail="Belum login")

    uploads = db.query(CVUpload).filter(CVUpload.user_id == user["id"]).order_by(CVUpload.created_at.desc()).all()

    return [
        {
            "id": u.id,
            "original_filename": u.original_filename,
            "keywords": json.loads(u.keywords),
            "created_at": u.created_at.isoformat()
        }
        for u in uploads
    ]

# === Chat lanjutan dengan LLM ===
@router.post("/chat")
async def chat_llm(payload: dict, request: Request = None, db: Session = Depends(get_db)):
    message = payload.get("message", "")
    upload_id = payload.get("upload_id")  # opsional

    if not message.strip():
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    try:
        user = request.session.get("user") if hasattr(request, "session") else None

        # Jika user tidak login, langsung kirim hasil Gemini tanpa simpan ke DB
        if not user:
            model = genai.GenerativeModel("models/gemini-2.0-flash")
            response = model.generate_content(message)
            return {"response": response.text}

        model = genai.GenerativeModel("models/gemini-2.0-flash")

        # Ambil teks CV & keyword (jika ada upload_id valid)
        cv_text = ""
        cv = None
        if upload_id:
            cv = db.query(CVUpload).filter(
                CVUpload.id == upload_id,
                CVUpload.user_id == user["id"]
            ).first()
            if not cv:
                raise HTTPException(status_code=403, detail="CV tidak ditemukan atau bukan milik Anda.")
            cv_text = cv.extracted_text

        prompt = (
            f"Berikut ini adalah isi CV dari pengguna:\n\n{cv_text}\n\n"
            f"Pengguna bertanya:\n{message}\n\n"
            f"Tugas Anda:\n"
            f"1. Jawablah pertanyaan berdasarkan isi CV di atas, baik secara langsung maupun implisit (misalnya: skill, pengalaman, minat).\n"
            f"2. Jika pertanyaannya terkait prospek kerja, industri, atau contoh perusahaan yang cocok dengan profil CV, berikan jawaban yang **spesifik dan aplikatif**.\n"
            f"3. **Gunakan format Markdown yang rapi**:\n"
            f"   - Gunakan heading dengan `##` untuk subjudul, dan `###` untuk bagian dalamnya.\n"
            f"   - Pisahkan **setiap heading** dengan **satu baris kosong di atas dan bawah**.\n"
            f"   - Gunakan bullet list (`-`) atau numbered list (`1.`) dengan **satu baris kosong sebelum list**.\n"
            f"   - Gunakan `**bold**` jika ingin menyorot istilah penting atau nama proyek.\n"
            f"   - Pisahkan paragraf dengan satu baris kosong.\n"
            f"4. Jika pertanyaan tidak relevan, tolak dengan sopan dan arahkan user kembali ke topik CV atau pekerjaan yang relevan.\n"
            f"5. Hindari jawaban yang terlalu umum. Buat jawaban terasa personal dan kontekstual.\n"
        )

        response = model.generate_content(prompt)
        response_text = response.text

        db.add_all([
            ChatHistory(
                user_id=user["id"],
                cv_upload_id=upload_id,
                role="user",
                message=message
            ),
            ChatHistory(
                user_id=user["id"],
                cv_upload_id=upload_id,
                role="llm",
                message=response_text
            )
        ])
        db.commit()

        return {"response": response_text}

    except Exception as e:
        print("[CHAT ERROR]")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan: {str(e)}")

@router.get("/chat-history/{upload_id}")
def get_chat_history(upload_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(status_code=401, detail="Belum login")

    chat = db.query(ChatHistory)\
        .filter(ChatHistory.user_id == user["id"])\
        .filter(ChatHistory.cv_upload_id == upload_id)\
        .order_by(ChatHistory.created_at.asc())\
        .all()

    return [
        {
            "role": c.role,
            "message": c.message,
            "created_at": c.created_at.isoformat()
        }
        for c in chat
    ]

@router.delete("/delete-upload/{upload_id}")
def delete_upload(upload_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(status_code=401, detail="Belum login")

    cv = db.query(CVUpload).filter(
        CVUpload.id == upload_id,
        CVUpload.user_id == user["id"]
    ).first()

    if not cv:
        raise HTTPException(status_code=404, detail="Upload tidak ditemukan atau bukan milik Anda.")

    # Hapus file PDF dari disk
    try:
        if os.path.exists(cv.saved_path):
            os.remove(cv.saved_path)
    except Exception as e:
        print(f"[FILE DELETE ERROR] {e}")

    # Hapus chat history & record CV
    db.query(ChatHistory).filter(ChatHistory.cv_upload_id == upload_id).delete()
    db.delete(cv)
    db.commit()

    return {"message": f"Upload CV dan histori chat berhasil dihapus."}