import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
from groq import Groq
import random
import os
from dotenv import load_dotenv

load_dotenv()


class SimpleAIChat:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Chat - Simple Test")
        self.root.geometry("600x500")
        
        # Initialize AI
        try:
            # โหลด environment variables
            load_dotenv()
            api_key = os.getenv('api_key')
            
            if not api_key:
                raise Exception("API key not found in .env file")
                
            self.client = Groq(api_key=api_key)
            self.model = "openai/gpt-oss-20b"
        except Exception as e:
            messagebox.showerror("Error", f"AI setup failed: {e}")
            return
        
        self.conversation_history = []  # เพิ่มตัวแปรเก็บประวัติการสนทนา
        self.dice_history = []  # เก็บประวัติการทอยลูกเต๋า
        
        self.setup_ui()
        
    def setup_ui(self):
        """สร้าง UI แบบเรียบง่าย"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Simple AI Chat", 
                 font=("Arial", 14, "bold")).pack(pady=(0, 10))
        
        # Chat area
        self.chat_text = scrolledtext.ScrolledText(
            main_frame, 
            height=20, 
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Arial", 10)
        )
        self.chat_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Input frame
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Input entry
        self.input_entry = ttk.Entry(input_frame, font=("Arial", 10))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.input_entry.bind('<Return>', lambda e: self.send_message())
        
        # Send button
        self.send_btn = ttk.Button(input_frame, text="Send", command=self.send_message)
        self.send_btn.pack(side=tk.RIGHT)
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="พร้อมแชท...")
        self.status_label.pack()
        
        # Welcome message
        self.add_message("AI", "ในโลกถูกแบ่งออกเป็น 4 ดินแดนใหญ่ แต่ละดินแดนถูกปกครองโดย “ผู้พิทักษ์ธาตุ” (Spirit Guardian) ที่ปกป้องสมดุลของโลกไว้ แต่เมื่อพลังมืดโบราณถูกปลุกขึ้นมา ผู้พิทักษ์ถูกบิดเบือนจิตใจจนกลายเป็น “ผู้พิทักษ์แห่งความมืด” ทำให้แต่ละดินแดนเริ่มพังทลาย ผู้เล่นต้องเดินทางผ่านทั้ง 4 ดินแดน กอบกู้พลังและคืนสมดุล ")
        
        # Focus to input
        self.input_entry.focus()
    
    def add_message(self, sender, message):
        """เพิ่มข้อความใน chat area"""
        self.chat_text.config(state=tk.NORMAL)
        
        if sender == "You":
            self.chat_text.insert(tk.END, f"You: {message}\n", "user")
        else:
            self.chat_text.insert(tk.END, f"AI: {message}\n\n", "ai")
        
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)
        
        # Configure colors
        self.chat_text.tag_configure("user", foreground="blue")
        self.chat_text.tag_configure("ai", foreground="green")
    
    def send_message(self):
        """ส่งข้อความ"""
        message = self.input_entry.get().strip()
        if not message:
            return
        
        # Clear input and disable controls
        self.input_entry.delete(0, tk.END)
        self.send_btn.config(state="disabled")
        self.input_entry.config(state="disabled")
        self.status_label.config(text="AI กำลังตอบ...")
        
        # Show user message
        self.add_message("You", message)
        
        # Get AI response in background
        threading.Thread(target=self.get_ai_response, args=(message,), daemon=True).start()
    
    def roll_dice(self, sides=20):
        """ทอยลูกเต๋า d4, d6, d8, d10, d12, d20 etc."""
        result = random.randint(1, sides)
        self.dice_history.append(result)
        return result

    def get_ai_response(self, message):
        """เรียก AI"""
        try:
            # สร้างการทอยลูกเต๋าล่วงหน้า
            d20_roll = self.roll_dice(20)
            
            # เพิ่มประวัติการสนทนา
            self.conversation_history.append({"role": "user", "content": message})
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"""คุณเป็น AI Game Master ที่จะต้อง:
                        1. ใช้ผลการทอยลูกเต๋า d20 ที่ได้ {d20_roll} ในการตัดสินใจครั้งนี้
                        2. แปลผลลูกเต๋าดังนี้:
                           - 1-5: ล้มเหลวอย่างยิ่ง
                           - 6-10: ล้มเหลวเล็กน้อย
                           - 11-15: สำเร็จเล็กน้อย
                           - 16-20: สำเร็จอย่างยิ่ง
                        3. บรรยายผลลัพธ์ตามผลลูกเต๋าที่ทอยได้
                    
                        4. เก็บบริบทของการสนทนาและการตัดสินใจ
                        5. ไม่พูดเรื่องนอกบริบทของเกม
                        6.โดยสถานการณ์ที่เจอ gm ต้องคิดว่าเหมาะสมกับการผจญภัยในโลกแฟนตาซี D&D โดยมีรายละเอียดดังนี้:
                            - สถานที่: ให้ gm บรรยายสถานที่ที่ผู้เล่นอยู่ เช่น ปราสาท โบสถ์ หมู่บ้าน หรือป่า
                            - สถานการณ์: ให้ gm บรรยายสถานการณ์ที่เกิดขึ้น เช่น การโจมตีจากมอนสเตอร์ เหตุการณ์อุปสรรค หรือการพบปะกับตัวละครอื่นๆ ให้ gm เสนอสถานการณ์ที่บังคับให้ผู้เล่นต้องเผชิญหน้าและตัดสินใจ เช่น การต่อสู้ การเจรจา หรือการสำรวจ
                        7. ผู้เล่นต้องตอบใน choice ที่ gm เสนอเท่านั้น
                        8.Main Quest:
                            - เข้าสู่โอเอซิสโบราณที่ถูกพายุทรายปิดกั้น

                            - ค้นหาน้ำตาแห่งโอเอซิสในสุสานใต้ทะเลทราย

                            - ต่อสู้กับผู้พิทักษ์ทะเลทราย (วิญญาณพายุทรายที่ถูกครอบงำ)
                             Reward:  น้ำตาแห่งโอเอซิส (ใช้เปิดทางสู่ป่า)



                        9. พูดคุยด้วยภาษาไทยที่สุภาพ กระชับ"""
                    },
                    *self.conversation_history[-5:]  # เก็บประวัติ 5 ข้อความล่าสุด
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            ai_message = response.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": ai_message})
            
            # Update UI in main thread
            self.root.after(0, self.handle_response, ai_message, None)
            
        except Exception as e:
            self.root.after(0, self.handle_response, None, str(e))
    
    def handle_response(self, ai_message, error):
        """จัดการ response"""
        # Enable controls
        self.send_btn.config(state="normal")
        self.input_entry.config(state="normal")
        self.input_entry.focus()
        
        if error:
            self.add_message("AI", f"ขออภัย เกิดข้อผิดพลาด: {error}")
            self.status_label.config(text="เกิดข้อผิดพลาด")
        else:
            self.add_message("AI", ai_message)
            self.status_label.config(text="พร้อมแชท...")
    
    def run(self):
        """เริ่มแอป"""
        self.root.mainloop()

if __name__ == "__main__":
    app = SimpleAIChat()
    app.run()