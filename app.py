from flask import Flask, redirect, request, jsonify, render_template, Response, session, stream_with_context
import sqlite3
import os
import re
import math
from fpdf import FPDF
import random
from flask import session
from flask import session, redirect, url_for

# --- RAG ---
from langchain_ollama import OllamaLLM
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")

app = Flask(__name__)
app.secret_key = SECRET_KEY

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

@app.route('/book-now')
def booking_page():
    return render_template('index.html')

@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    try:
        data = request.json
        adults = int(data.get('adults', 1))
        nights = int(data.get('nights', 1))
        occ_type = data.get('occupancy', 'Double')
        
        # Room Calculation (2 adults per room for Double, 3 for Triple)
        rooms = (adults + 1) // 2 if occ_type == 'Double' else (adults + 2) // 3
        room_rate = 2000 if occ_type == 'Double' else 2300
        room_subtotal =int(rooms) * int(nights) * int(room_rate)
        
        # Meal Calculation
        m = data.get('meals', {})
        meal_unit_cost = (250 if m.get('breakfast') else 0) + \
                         (350 if m.get('lunch') else 0) + \
                         (350 if m.get('dinner') else 0)
        
        meal_subtotal = int(meal_unit_cost) * int(adults) * int(nights)
        grand_total = int(room_subtotal) + int(meal_subtotal)
        advance = grand_total * 0.40

        # PDF Generation
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, "MEERA VALLEY RESORT - QUOTATION", ln=True, align='C')
        pdf.ln(10)

        # Table Header
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(100, 10, "Description", border=1)
        pdf.cell(90, 10, "Details", border=1, ln=True)
        
        # Table Content
        pdf.set_font("Arial", '', 12)
        pdf.cell(100, 10, "Guests / Nights", border=1)
        pdf.cell(90, 10, f"{adults} Adults / {nights} Nights", border=1, ln=True)
        pdf.cell(100, 10, "Room Total", border=1)
        pdf.cell(90, 10, f"Rs {room_subtotal} ({rooms} Rooms)", border=1, ln=True)
        pdf.cell(100, 10, "Meal Total", border=1)
        pdf.cell(90, 10, f"Rs {meal_subtotal}", border=1, ln=True)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(100, 10, "GRAND TOTAL", border=1)
        pdf.cell(90, 10, f"Rs {grand_total}", border=1, ln=True)
        
        pdf.set_text_color(200, 0, 0)
        pdf.cell(190, 10, f"40% Advance Required: Rs {advance}", border=1, ln=True, align='C')
        pdf.set_text_color(0, 0, 0)
        
        # Meal Menu Section
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, "Included Menu Details:", ln=True)
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 5, "Breakfast: Puri Bhaji, Upma, Bread Butter, Tea & Coffee\n"
                             "Lunch: Dal Makhani, Paneer Lababdar, Sev Tomato, Jeera Rice, Roti, Sweet\n"
                             "Dinner: Dal Fry, Paneer Butter Masala, Mix Veg, Veg Pulao, Roti, Sweet")

        filename = f"quote_{adults}pax.pdf"
        pdf_path = os.path.join(QUOTE_DIR, filename)
        pdf.output(pdf_path)

        return jsonify({'pdf_url': f'/{pdf_path}', 'grand_total': grand_total, 'advance': advance})
    
    except Exception as e:
        print(f"PDF Error: {e}")
        return jsonify({'error': "Could not generate quotation"}), 500


# ==============================
# 🗄 DATABASE SETUP
# ==============================
def init_db():
    conn = sqlite3.connect("bookings.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          booking_reference TEXT,
          name TEXT,
          email TEXT,
          phone TEXT,
          checkin_date TEXT,
          checkout_date TEXT,
          guests INTEGER,
          rooms INTEGER,
          occupancy TEXT,
          meals TEXT,
          amount INTEGER,
          status TEXT,
          created_at TEXT
    )
    """)
    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guest_name TEXT NOT NULL,
          rating INTEGER NOT NULL,
          review_text TEXT NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   )
   """)
    conn.commit()
    conn.close()

init_db()

# ==============================
# 📄 PDF QUOTATION SETUP
# ==============================
QUOTE_DIR = 'static/quotes'
if not os.path.exists(QUOTE_DIR):
    os.makedirs(QUOTE_DIR)

def generate_quotation_pdf(guests, days, meal_choice, occupancy_choice):
    # --- NEW ROOM CALCULATION ---
    occ_choice = occupancy_choice.lower()
    
    if "triple" in occ_choice:
        rooms = (guests + 2) // 3  # Rounds up: e.g., 4 guests = 2 rooms
        room_rate = 2300
        occ_type = "Triple"
    else:
        # Default to Double if they say "Double" or anything else
        rooms = (guests + 1) // 2  # Rounds up: e.g., 3 guests = 2 rooms
        room_rate = 2000
        occ_type = "Double"
        
    room_total = (rooms * room_rate) * int(days)
    
    # --- MEAL CALCULATION (Unchanged) ---
    meal_choice = meal_choice.lower()
    
    if "all" in meal_choice or "yes" in meal_choice:
        meal_rate_per_day = 950 
        meal_type = "All Meals"
    elif "breakfast" in meal_choice and "lunch" in meal_choice:
        meal_rate_per_day = 600 
        meal_type = "Breakfast & Lunch"
    elif "breakfast" in meal_choice and "dinner" in meal_choice:
        meal_rate_per_day = 600 
        meal_type = "Breakfast & Dinner"
    elif "lunch" in meal_choice and "dinner" in meal_choice:
        meal_rate_per_day = 700 
        meal_type = "Lunch & Dinner"
    elif "lunch" in meal_choice:
        meal_rate_per_day = 350 
        meal_type = "Lunch Only"
    elif "dinner" in meal_choice:
        meal_rate_per_day = 350 
        meal_type = "Dinner Only"
    elif "breakfast" in meal_choice:
        meal_rate_per_day = 250 
        meal_type = "Breakfast Only"
    else:
        meal_rate_per_day = 0
        meal_type = "Room Only (No Meals)"
        
    meal_total = int(guests) * int(days) * int(meal_rate_per_day)
    grand_total = room_total + meal_total
    advance = grand_total * 0.40
    
    # --- PDF BUILDER ---
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, "MEERA VALLEY RESORT - QUOTATION", ln=True, align='C')
    pdf.ln(10)

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Description", border=1)
    pdf.cell(90, 10, "Details", border=1, ln=True)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 10, "Guests / Nights", border=1)
    pdf.cell(90, 10, f"{guests} Guests / {days} Nights", border=1, ln=True)
    
    # Updated PDF row to show occupancy type
    pdf.cell(100, 10, "Room Total", border=1)
    pdf.cell(90, 10, f"Rs {room_total} ({rooms} {occ_type} Rooms)", border=1, ln=True)
    
    pdf.cell(100, 10, "Meal Total", border=1)
    pdf.cell(90, 10, f"Rs {meal_total} ({meal_type})", border=1, ln=True)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "GRAND TOTAL", border=1)
    pdf.cell(90, 10, f"Rs {grand_total}", border=1, ln=True)
    
    pdf.set_text_color(200, 0, 0)
    pdf.cell(190, 10, f"40% Advance Required: Rs {advance}", border=1, ln=True, align='C')
    pdf.set_text_color(0, 0, 0)
    
    if meal_rate_per_day > 0:
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, "Included Menu Details:", ln=True)
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 5, "Breakfast: Puri Bhaji, Upma, Bread Butter, Tea & Coffee\n"
                             "Lunch: Dal Makhani, Paneer Lababdar, Sev Tomato, Jeera Rice, Roti, Sweet\n"
                             "Dinner: Dal Fry, Paneer Butter Masala, Mix Veg, Veg Pulao, Roti, Sweet")

    filename = f"quote_{guests}pax_{days}nights.pdf"
    filepath = os.path.join(QUOTE_DIR, filename)
    pdf.output(filepath)
    
    safe_url = filepath.replace("\\", "/")
    return safe_url, grand_total, advance

# ==============================
# 🤖 RAG SETUP (Local AI)
# ==============================
# ==============================
# 🤖 RAG SETUP (DUAL SYSTEM)
# ==============================
try:
    splitter = RecursiveCharacterTextSplitter(
    chunk_size=120,
    chunk_overlap=30
    )

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # -------- RESORT RAG --------
    resort_loader = TextLoader("resort_knowledge.txt")
    resort_docs = resort_loader.load()
    resort_texts = splitter.split_documents(resort_docs)

    resort_vectorstore = Chroma.from_documents(
        resort_texts, embeddings, persist_directory="./chroma_resort"
    )

    resort_retriever = resort_vectorstore.as_retriever(search_kwargs={"k": 3})

    # -------- UDAIPUR RAG --------
    udaipur_loader = TextLoader("udaipur_knowledge.txt")
    udaipur_docs = udaipur_loader.load()
    udaipur_texts = splitter.split_documents(udaipur_docs)

    udaipur_vectorstore = Chroma.from_documents(
        udaipur_texts, embeddings, persist_directory="./chroma_udaipur"
    )

    udaipur_retriever = udaipur_vectorstore.as_retriever(search_kwargs={"k": 3})

    llm = OllamaLLM(model="phi3")

except Exception as e:
    print("RAG ERROR:", e)
    resort_retriever = None
    udaipur_retriever = None
    llm = None

# ==============================
# 🎭 AI PROMPT TEMPLATE
# ==============================
CONCIERGE_TEMPLATE = """You are a professional, polite, and welcoming AI concierge for Meera Valley Resort in Udaipur.
Your goal is to assist guests with their inquiries using ONLY the provided context.

Rules:
1. Be warm and hospitable.
2. If the answer is not in the context, do NOT guess or make up information. 
3. If you don't know the answer, politely tell the guest to contact the resort directly at 8905756778 or hmeerapalace@gmail.com.
4. Keep your answers clear and concise.
5. There are 20 rooms in the resort. only say this if the user asks about room availability or total rooms.
6. Do not make answers more than 3 sentences long.
7. DO NOT make up answers about the resort's facilities, services, or policies. If it's not in the context, say you don't have that information.

Context Information:
{context}

Guest Question:
{question}

Concierge Response:"""

# ==============================
# 🧠 SESSION & INTENT HELPERS
# ==============================
sessions = {}

def detect_intent(q):
    q = q.lower()
    
    # Now it understands that saying "yes" or "sure" means they want to book
    if any(word in q for word in ["book", "reserve", "yes", "sure", "yeah", "ok"]):
        return "booking"
        
    # Added "quotation" and "quote" so it triggers the price flow
    if any(word in q for word in ["price", "cost", "rate", "quotation", "quote"]):
        if any(word in q for word in ["breakfast", "lunch", "dinner", "meal", "meals","venue","wedding"]):
            return "general"
        return "price"
        
    if any(word in q for word in ["hi", "hello", "hey"]):
        return "greeting"
        
    return "general"

def get_resort_context(query):
    if not resort_retriever:
        return ""
    docs = resort_retriever.invoke(query)
    return "\n".join([d.page_content for d in docs])


def get_udaipur_context(query):

    if not udaipur_retriever:
        return ""

    docs = udaipur_retriever.invoke(query)

    unique_chunks = []
    seen = set()

    for doc in docs:
        text = doc.page_content.strip()

        if text not in seen:
            seen.add(text)
            unique_chunks.append(text)

    return "\n\n".join(unique_chunks)

def parse_date(date_str):

    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        return datetime.strptime(date_str, "%d-%m-%Y")

def send_email(to_email, subject, body):
    try:
        print(f"Sending email to: {to_email}")

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_EMAIL
        msg["To"] = to_email

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()

        server.login(
            SMTP_EMAIL,
            SMTP_PASSWORD
        )

        server.send_message(msg)
        server.quit()

        print("EMAIL SENT SUCCESSFULLY")

    except Exception as e:
        print("EMAIL ERROR:", str(e))
    
def save_booking(session):

    booking_ref = "MVR-" + datetime.now().strftime("%Y%m%d%H%M%S")

    created_at = datetime.now().strftime(
        "%d-%m-%Y %H:%M:%S"
    )

    conn = sqlite3.connect("bookings.db")
    c = conn.cursor()

    c.execute("""
    INSERT INTO bookings
    (
        booking_reference,
        name,
        email,
        phone,
        checkin_date,
        checkout_date,
        guests,
        rooms,
        occupancy,
        meals,
        amount,
        status,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        booking_ref,
        session["name"],
        session["email"],
        session["phone"],
        session["checkin_date"],
        session["checkout_date"],
        session["guests"],
        session["rooms"],
        session["occupancy"],
        session["meals"],
        session["amount"],
        "PENDING",
        created_at
    ))

    conn.commit()
    conn.close()

    return booking_ref

def notify_owner(session, booking_ref):

    body = f"""
NEW BOOKING REQUEST

Reference:
{booking_ref}

Name:
{session['name']}

Email:
{session['email']}

Phone:
{session['phone']}

Check-in:
{session['checkin_date']}

Check-out:
{session['checkout_date']}

Guests:
{session['guests']}

Occupancy:
{session['occupancy']}

Meals:
{session['meals']}

Amount:
Rs {session['amount']}
"""

    send_email(
        ADMIN_EMAIL,
        f"Booking Request {booking_ref}",
        body
    )
    
def send_confirmation_email(booking):

    body = f"""
Dear {booking['name']},

Greetings from Meera Valley Resort, Udaipur!

We are pleased to confirm your booking.

Booking Reference:
{booking['booking_reference']}

Check-In:
{booking['checkin_date']}

Check-Out:
{booking['checkout_date']}

Guests:
{booking['guests']}

Thank you for choosing Meera Valley Resort.

For any assistance:
Phone: 8905756778
Email: hmeerapalace@gmail.com

We look forward to welcoming you.

Regards,
Meera Valley Resort
"""

    send_email(
        booking["email"],
        "Booking Confirmed - Meera Valley Resort",
        body
    )
    
def rooms_available(checkin_date, checkout_date):

    conn = sqlite3.connect("bookings.db")
    conn.row_factory = sqlite3.Row

    bookings = conn.execute("""
        SELECT *
        FROM bookings
        WHERE status IN ('PENDING','CONFIRMED')
    """).fetchall()

    conn.close()

    occupied_rooms = 0

    requested_checkin = parse_date(checkin_date)
    requested_checkout = parse_date(checkout_date)

    for booking in bookings:

        existing_checkin = parse_date(booking["checkin_date"])
        existing_checkout = parse_date(booking["checkout_date"])

        overlap = (
            requested_checkin < existing_checkout and
            requested_checkout > existing_checkin
        )

        if overlap:

            occupied_rooms += booking["rooms"]

    return 20 - occupied_rooms

# ==============================
# 🌐 ROUTES
# ==============================
@app.route('/')
def home():
    return render_template("frontend.html")

@app.route('/chat', methods=['POST'])
def chat():
    msg = request.json.get("message")
    
    user_id = request.remote_addr
    if user_id not in sessions:
        sessions[user_id] = {}

    session = sessions[user_id]
    
    # Escape Hatch
    if any(word in msg.lower() for word in ["cancel", "stop", "exit", "reset", "nevermind"]):
        sessions[user_id] = {} 
        return Response("Okay, I have cancelled that process. What else can I help you with?", mimetype='text/plain')

    # --- 1. HANDLE ONGOING BOOKING FLOW ---
   # --- 1. HANDLE ONGOING BOOKING FLOW ---
    # Added "occupancy" to the list of steps here
    if session.get("step") in ["name","email","phone","checkin","checkout","guests", "occupancy", "meals"]:
        
        if session.get("step") == "name":
            session["name"] = msg
            session["step"] = "email"
            return Response("Great! Please enter your email address.", mimetype='text/plain')
        
        if session.get("step") == "email":
            session["email"] = msg
            session["step"] = "phone"
            return Response("Great! Please enter your phone number.", mimetype='text/plain')

        if session.get("step") == "phone":
            session["phone"] = msg
            session["step"] = "checkin"
            return Response("Please enter your check-in date (YYYY-MM-DD).",mimetype='text/plain')
        
        if session.get("step") == "checkin":
           session["checkin_date"] = msg
           session["step"] = "checkout"
           return Response("Please enter your check-out date (YYYY-MM-DD).",mimetype='text/plain')
       
        if session.get("step") == "checkout":
           session["checkout_date"] = msg
           checkin = datetime.strptime(
               session["checkin_date"],
               "%Y-%m-%d"
            )
           today = datetime.now().date()
           
           if checkin.date() < today:
               return Response(
               "Check-in date cannot be in the past.",
               mimetype='text/plain'
        )
           checkout = datetime.strptime(
               session["checkout_date"],
               "%Y-%m-%d"
           )
           if checkout <= checkin:
               return Response(
               "Check-out date must be after check-in date.",
               mimetype='text/plain'
            )

           session["days"] = (
               checkout - checkin
            ).days

           session["step"] = "guests"

           return Response(
               "How many guests will be staying?",
                mimetype='text/plain'
                )

        if session.get("step") == "guests":
            match = re.search(r'\d+', msg)
            if match:
                session["guests"] = int(match.group())
                session["step"] = "occupancy"
                return Response("Would you prefer Double or Triple occupancy rooms? (Reply 'Double' or 'Triple')", mimetype='text/plain')
            else:
                return Response("Please enter a valid output.", mimetype='text/plain')

        

        # NEW: The occupancy handler
        if session.get("step") == "occupancy":
            session["occupancy"] = msg
            session["step"] = "meals"
            return Response("Would you like to add meals? Reply with 'All meals', 'Breakfast', or 'No'.", mimetype='text/plain')

        if session.get("step") == "meals":
            session["meals"] = msg
            try:
                if (
                   "checkin_date" in session and
                   "checkout_date" in session and
                   "guests" in session and
                   "occupancy" in session
                ):
                    available_rooms = rooms_available(
                       session["checkin_date"],
                       session["checkout_date"]
                    )
                    guests = int(session["guests"])

                    if "triple" in session["occupancy"].lower():
                       required_rooms = (int(session["guests"]) + 2) // 3
                    else:
                       required_rooms = (int(session["guests"]) + 1) // 2
                    session["rooms"] = required_rooms

                    if required_rooms > available_rooms:

                       return Response(
                         f"""
Sorry, only {available_rooms} room(s) are available for those dates.

Please select different dates or reduce the number of guests.
""",
                         mimetype='text/plain'
                        )
                # NEW: Pass all 4 pieces of info into our updated PDF generator
                pdf_url, amount, advance = generate_quotation_pdf(
                    session["guests"], 
                    session["days"], 
                    session["meals"], 
                    session["occupancy"]
                )
                
                session["amount"] = amount
                session["step"] = "payment"
                
                reply_msg = f"Your quotation is ready! Your total is Rs {amount}.<br><br>"
                reply_msg += f"📄 <a href='/{pdf_url}' target='_blank' style='color:#C9A84C; font-weight:bold; text-decoration:underline;'>Click here to download your PDF Quotation</a><br><br>"
                reply_msg += """
<br><br>

To submit this booking request, type:

<b>Confirm Booking</b>
"""
                return Response(reply_msg, mimetype='text/plain')
                
            except Exception as e:
                print(f"PDF Error: {e}")
                return Response("I calculated your total, but had trouble generating the PDF. Please try again!", mimetype='text/plain')
    
    if session.get("step") == "verify_booking_otp":

        if msg.strip() != session.get("booking_otp"):

            return Response(
                "Invalid OTP. Please enter the correct verification code.",
                mimetype="text/plain"
           )

        required_fields = [
            "checkin_date",
            "checkout_date",
            "guests",
            "occupancy"
        ]

        for field in required_fields:
            if field not in session:
                return Response(
                    f"Booking information missing: {field}",
                    mimetype="text/plain"
                )

        available = rooms_available(
            session["checkin_date"],
            session["checkout_date"]
        )

        guests = int(session["guests"])

        if session["occupancy"].lower() == "triple":
            required_rooms = math.ceil(guests / 3)
        else:
            required_rooms = math.ceil(guests / 2)

        session["rooms"] = required_rooms

        if required_rooms > available:

            return Response(
                f"""
Sorry.

Only {available} room(s) are available for the selected dates.

Please choose different dates.
""",
                mimetype="text/plain"
            )

        booking_ref = save_booking(session)

        notify_owner(
            session,
            booking_ref
        )

        send_email(
            session["email"],
            "Booking Request Received",
            f"""
Dear {session['name']},

Thank you for choosing Meera Valley Resort.

We have received your booking request.

Reference:
{booking_ref}

Our team will review your request shortly.

Regards,
Meera Valley Resort
"""
        )
        session.pop("booking_otp", None)

        session["step"] = "booking_complete"

        return Response(
            f"""
Booking request submitted successfully.

Reference:
{booking_ref}

Our team will contact you shortly.
    """,
            mimetype="text/plain"
        )  
            
    if msg.lower().strip() == "confirm booking":

        otp = str(random.randint(100000, 999999))

        session["booking_otp"] = otp
        session["step"] = "verify_booking_otp"

        send_email(
            session["email"],
            "Meera Valley Resort Booking Verification",
            f"""
Dear {session['name']},

Your booking verification code is:

{otp}

Regards,
Meera Valley Resort
"""
        )

        return Response(
            """
Verification code has been sent to your email.

Please enter the 6-digit OTP to continue.
    """,
            mimetype="text/plain"
      )
        
 
    # --- 2. DETECT NEW INTENT ---
    intent = detect_intent(msg)

    if intent == "greeting":
        return Response("Hello! Welcome to Meera Valley Resort 😊 How can I help you today?", mimetype='text/plain')

    if intent == "price":
        return Response("Our Double Occupancy rooms start at Rs 2000 per night, and Triple Occupancy is Rs 2300 per night. Would you like to start a booking?", mimetype='text/plain')

    if intent == "booking":
        session["step"] = "name"
        return Response("I'd be happy to help you book a stay. To get started, please enter your name.", mimetype='text/plain')

    # --- 3. FALLBACK TO LOCAL AI RAG (STREAMING ENABLED) ---
    if intent == "general":
        if not llm:
            return Response("My knowledge base is offline right now. Please check the server console.", mimetype='text/plain')
        
        context = get_resort_context(msg)
        prompt = CONCIERGE_TEMPLATE.format(context=context, question=msg)
        
        try:
            # The Generator function that streams words as they are created
            def generate_stream():
                for chunk in llm.stream(prompt):
                    yield chunk
            
            return Response(stream_with_context(generate_stream()), mimetype='text/plain')
            
        except Exception as e:
            print("LLM Generation Error:", e)
            return Response("I'm having a little trouble thinking right now. Please try asking again.", mimetype='text/plain')

    return Response("I am not sure how to respond to that. Could you rephrase?", mimetype='text/plain')


# ==============================
# 💳 PAYMENT WEBHOOK VERIFY
# ==============================
@app.route('/payment-success', methods=['POST'])
def payment_success():
    data = request.json

    conn = sqlite3.connect("bookings.db")
    c = conn.cursor()

    c.execute("""
    INSERT INTO bookings (name, phone, guests, days, amount, payment_id, status)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("name"),
        data.get("phone"),
        data.get("guests"),
        data.get("days"),
        data.get("amount"),
        data.get("payment_id"),
        "PAID"
    ))

    conn.commit()
    conn.close()

    return jsonify({"status": "saved"})

# --- NEW: ITINERARY PLANNER PROMPT ---
ITINERARY_TEMPLATE = """You are an expert AI Tourist guide for Udaipur, Rajasthan. 
A guest staying at the Meera Valley Resort wants you to build a personalized itinerary and answer their questions.

Rules:
1. If they haven't given you preferences, ask them: How many days? Who are they traveling with? Do they prefer culture, nature, or relaxation?
2. Suggest real Udaipur attractions (City Palace, Lake Pichola, Sajjangarh Monsoon Palace, Saheliyon Ki Bari).
3. Always suggest starting at Meera Valley Resort.
4. Keep the tone enthusiastic, welcoming, and organized. Use bullet points for daily plans.
5. Base it on the user's preferences if they provided them.
6. Use ONLY the provided context.
7. Never make up facts.

Guest: {question}
Planner Response:"""

# ==============================
# 🗺️ ITINERARY PAGE ROUTE (Add this!)
# ==============================
# ==============================
# 🗺️ ITINERARY PAGE ROUTE (Add this!)
# ==============================
@app.route('/itinerary')
def itinerary_page():
    return render_template('itenary.html')

# --- NEW: ITINERARY PLANNER PROMPT ---
ITINERARY_TEMPLATE = """You are a Udaipur tourist guide and travel planner.

RULES:
- Only use Udaipur places
- Do NOT include other cities
- Do NOT repeat places
- Keep answer short and structured
- DO NOT make up place names or change them.

Guest: {question}
Answer:"""

@app.route('/itinerary-chat', methods=['POST'])
def itinerary_chat():
    msg = request.json.get("message")
    
    # Format the prompt with the user's message
    context = get_udaipur_context(msg)
    
    print("\n==========================")
    print("USER QUESTION:", msg)
    print("==========================")
    print(context)
    print("==========================\n")

    prompt = f"""
You are a professional Udaipur Travel Assistant.

IMPORTANT:
You may ONLY use the places listed below.

ALLOWED PLACES:
City Palace
Lake Pichola
Fateh Sagar Lake
Sajjangarh Monsoon Palace
Saheliyon Ki Bari
Jagdish Temple
Bagore Ki Haveli
Shilpgram
Neemach Mata Temple
Meera Valley Resort

If a place is not in the list above, DO NOT mention it.

For itineraries:
- Start every day from Meera Valley Resort.
- End every day at Meera Valley Resort.
- Use only places from the allowed list.
- Do not invent hotels.
- Do not invent restaurants.
- Do not invent timings.
- Do not invent activities.
- Keep the itinerary under 150 words.

CONTEXT:
{context}

QUESTION:
{msg}

ANSWER:
"""
    
    try:
        # Stream the response back just like the main chat!
        def generate_stream():
            full_text = ""
            for chunk in llm.stream(prompt):
                full_text += chunk
                yield chunk
        
        return Response(stream_with_context(generate_stream()), mimetype='text/plain')
        
    except Exception as e:
        print("LLM Itinerary Error:", e)
        return Response("I'm having trouble planning right now. Please try again.", mimetype='text/plain')
    
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        if (
            username == os.getenv("ADMIN_USERNAME")
            and
            password == os.getenv("ADMIN_PASSWORD")
        ):

            session['admin_logged_in'] = True

            return redirect('/admin/bookings')

        return "Invalid Username or Password"

    return render_template('admin_login.html')
    
@app.route('/admin/bookings')
def admin_bookings():

    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    conn = sqlite3.connect("bookings.db")
    conn.row_factory = sqlite3.Row

    bookings = conn.execute(
        "SELECT * FROM bookings ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "admin_bookings.html",
        bookings=bookings
    )

@app.route('/approve/<int:id>')
def approve_booking(id):

    conn = sqlite3.connect("bookings.db")
    conn.row_factory = sqlite3.Row

    booking = conn.execute(
        "SELECT * FROM bookings WHERE id=?",
        (id,)
    ).fetchone()

    conn.execute(
        """
        UPDATE bookings
        SET status='CONFIRMED'
        WHERE id=?
        """,
        (id,)
    )

    conn.commit()
    conn.close()

    send_confirmation_email(booking)

    return f"""
Booking Confirmed

Reference:
{booking['booking_reference']}

Confirmation email sent to:
{booking['email']}
"""

@app.route('/reject/<int:id>')
def reject_booking(id):

    conn = sqlite3.connect("bookings.db")
    conn.row_factory = sqlite3.Row

    booking = conn.execute(
        "SELECT * FROM bookings WHERE id=?",
        (id,)
    ).fetchone()

    conn.execute(
        """
        UPDATE bookings
        SET status='REJECTED'
        WHERE id=?
        """,
        (id,)
    )

    conn.commit()
    conn.close()

    send_email(
        booking["email"],
        "Booking Request Update - Meera Valley Resort",
        f"""
Dear {booking['name']},

Thank you for choosing Meera Valley Resort.

Unfortunately, we are unable to confirm your booking for the requested dates.

Booking Reference:
{booking['booking_reference']}

Please contact us at:
Phone: 8905756778
Email: hmeerapalace@gmail.com

We would be happy to assist you with alternate dates.

Regards,
Meera Valley Resort
"""
    )

    return f"""
Booking Rejected

Reference:
{booking['booking_reference']}

Rejection email sent to:
{booking['email']}
"""
@app.route('/admin/logout')
def admin_logout():

    session.clear()

    return redirect('/admin/login')

@app.route('/reviews')
def reviews():

    conn = sqlite3.connect("bookings.db")
    conn.row_factory = sqlite3.Row

    reviews = conn.execute("""
        SELECT *
        FROM reviews
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "reviews.html",
        reviews=reviews
    )

@app.route('/submit-review', methods=['POST'])
def submit_review():

    name = request.form['name']
    rating = request.form['rating']
    review = request.form['review']

    conn = sqlite3.connect("bookings.db")

    conn.execute("""
    INSERT INTO reviews
    (
        guest_name,
        rating,
        review_text
    )
    VALUES (?, ?, ?)
    """,
    (
        name,
        rating,
        review
    ))

    conn.commit()
    conn.close()

    return redirect('/reviews')

@app.route('/send-booking-otp', methods=['POST'])
def send_booking_otp():

    email = request.form['email']

    otp = str(random.randint(100000, 999999))

    session['booking_otp'] = otp

    send_email(
        email,
        "Meera Valley Resort Verification Code",
        f"""
Your verification code is:

{otp}

Please enter this code to complete your booking.
"""
    )

    return {"success": True}

@app.route('/create-booking', methods=['POST'])
def create_booking():

    import sqlite3
    import uuid
    from datetime import datetime
    entered_otp = request.form['otp']

    saved_otp = session.get('booking_otp')

    if entered_otp != saved_otp:

       return """
       <h2>Invalid Verification Code</h2>
       <a href='/'>Try Again</a>
       """

    booking_reference = "MVR-" + str(uuid.uuid4())[:8].upper()
    guests = int(request.form['guests'])
    occupancy = request.form['occupancy']

    if occupancy == "Double":
       rooms_required = math.ceil(guests / 2)
    else:
       rooms_required = math.ceil(guests / 3)

    if rooms_required > 20:
       return """
    <h2>Booking Failed</h2>
    <p>Sorry, Meera Valley Resort has only 20 rooms available.</p>
    <a href='/book-now'>Go Back</a>
    """

    name = request.form['name']
    email = request.form['email']
    phone = request.form['phone']
    checkin_date = request.form['checkin_date']
    checkout_date = request.form['checkout_date']
    guests = request.form['guests']
    rooms = rooms_required
    occupancy = request.form['occupancy']
    meals = request.form['meals']
    amount = request.form['amount']

    conn = sqlite3.connect("bookings.db")

    checkin = request.form['checkin_date']
    checkout = request.form['checkout_date']

    available_rooms = rooms_available(
        checkin_date,
        checkout_date
    )

    if rooms_required > available_rooms:

        conn.close()

        return f"""
        <h2>Booking Failed</h2>
        <p>
        Only {available_rooms} room(s) are available
        for the selected dates.
        </p>
        <a href='/book-now'>Go Back</a> 
        """
    conn.execute("""
    INSERT INTO bookings
    (
        booking_reference,
        name,
        email,
        phone,
        checkin_date,
        checkout_date,
        guests,
        rooms,
        occupancy,
        meals,
        amount,
        status,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        booking_reference,
        name,
        email,
        phone,
        checkin_date,
        checkout_date,
        guests,
        rooms,
        occupancy,
        meals,
        amount,
        "PENDING",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    # ==========================
    # EMAIL TO CUSTOMER
    # ==========================

    try:

        send_email(
            email,
            "Booking Request Received - Meera Valley Resort",
            f"""
Dear {name},

Thank you for choosing Meera Valley Resort.

We have successfully received your booking request.

Booking Reference:
{booking_reference}

Check-In:
{checkin_date}

Check-Out:
{checkout_date}

Guests:
{guests}

Rooms:
{rooms}

Meal Plan:
{meals}

Amount:
Rs {amount}

Our team will review your request and contact you shortly.

Regards,
Meera Valley Resort
Phone: 8905756778
Email: hmeerapalace@gmail.com
"""
        )

        print("Customer email sent successfully")

    except Exception as e:

        print("Customer email error:", e)

    # ==========================
    # EMAIL TO OWNER
    # ==========================

    try:

        send_email(
            ADMIN_EMAIL,
            f"New Booking Request - {booking_reference}",
            f"""
NEW BOOKING REQUEST

Reference:
{booking_reference}

Name:
{name}

Email:
{email}

Phone:
{phone}

Check-In:
{checkin_date}

Check-Out:
{checkout_date}

Guests:
{guests}

Rooms:
{rooms}

Occupancy:
{occupancy}

Meals:
{meals}

Amount:
Rs {amount}

Status:
PENDING
"""
        )

        print("Owner email sent successfully")

    except Exception as e:

        print("Owner email error:", e)

    return f"""
    <html>
    <head>
        <title>Booking Submitted</title>
    </head>

    <body style="font-family:Arial;text-align:center;padding-top:100px;">

        <h2 style="color:green;">
            Booking Submitted Successfully
        </h2>

        <h3>
            Reference: {booking_reference}
        </h3>

        <p>
            A confirmation email has been sent to:
            <b>{email}</b>
        </p>

        <br>

        <a href="/"
           style="
           background:#d4af37;
           color:black;
           padding:12px 25px;
           text-decoration:none;
           border-radius:6px;
           font-weight:bold;">
           Return Home
        </a>

    </body>
    </body>
    </html>
    """
# ==============================
# 🚀 RUN FLASK
# ==============================
if __name__ == "__main__":
    app.run(debug=True)
