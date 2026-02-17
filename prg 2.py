import os
from google import genai
import speech_recognition as sr
import re
import sys 
import schemdraw
import schemdraw.elements as elm
from collections import defaultdict
import json
from datetime import datetime

# --- ۱. تنظیمات API و احراز هویت ---
os.environ['GEMINI_API_KEY'] = "AIzaSyAQFq9vrRq3VoWszLIfhwi6lkh_3RWtFNE"
if 'GEMINI_API_KEY' not in os.environ:
    print("❌ اخطار: کلید API جِمنای در متغیر محیطی GEMINI_API_KEY تنظیم نشده است.")
    sys.exit(1)

# --- ۲. توابع تحلیل و رسم شماتیک ---

def parse_netlist(text):
    """تبدیل متن نت‌لیست به لیست قطعات"""
    components = []
    for line in text.strip().split('\n'):
        line = line.strip()
        
        if not line or line.startswith('*') or line.startswith('.'):
            continue
        
        parts = line.split()
        if len(parts) < 3:
            continue
        
        comp_type = parts[0][0].upper()
        name = parts[0]
        
        if comp_type in ['D']:
            if len(parts) < 3:
                continue
            node1, node2 = parts[1], parts[2]
            value = parts[3] if len(parts) > 3 else "1N4148"
            components.append({
                'type': comp_type,
                'name': name,
                'node1': node1,
                'node2': node2,
                'value': value,
                'pins': 2
            })
        elif comp_type in ['Q']:
            if len(parts) < 4:
                continue
            collector, base, emitter = parts[1], parts[2], parts[3]
            model = parts[4] if len(parts) > 4 else "2N2222"
            components.append({
                'type': comp_type,
                'name': name,
                'collector': collector,
                'base': base,
                'emitter': emitter,
                'node1': collector,  # برای الگوریتم مسیریابی
                'node2': emitter,
                'value': model,
                'pins': 3
            })
        elif comp_type in ['M']:
            if len(parts) < 5:
                continue
            drain, gate, source, body = parts[1], parts[2], parts[3], parts[4]
            model = parts[5] if len(parts) > 5 else "IRF530"
            components.append({
                'type': comp_type,
                'name': name,
                'drain': drain,
                'gate': gate,
                'source': source,
                'body': body,
                'node1': drain,  # برای الگوریتم مسیریابی
                'node2': source,
                'value': model,
                'pins': 4
            })
        elif comp_type in ['U', 'X']:
            # آپ‌امپ یا IC
            # فرمت: U1 out in+ in- vcc vee model
            if len(parts) < 4:
                continue
            
            # استخراج نودها و مدل
            all_nodes = parts[1:-1]  # همه به جز نام و مدل
            model = parts[-1]
            
            # برای آپ‌امپ معمولی: out, in+, in-, vcc, vee
            comp_data = {
                'type': comp_type,
                'name': name,
                'all_nodes': all_nodes,
                'value': model,
                'pins': len(all_nodes)
            }
            
            # اگر نودهای کافی داریم، آنها را نام‌گذاری کنیم
            if len(all_nodes) >= 3:
                comp_data['out'] = all_nodes[0]
                comp_data['in_p'] = all_nodes[1]
                comp_data['in_n'] = all_nodes[2]
                comp_data['node1'] = all_nodes[1]  # ورودی برای مسیریابی
                comp_data['node2'] = all_nodes[0]  # خروجی
            
            if len(all_nodes) >= 5:
                comp_data['vcc'] = all_nodes[3]
                comp_data['vee'] = all_nodes[4]
            
            components.append(comp_data)
        else:  # R, C, L, V
            if len(parts) < 4:
                continue
            node1, node2 = parts[1], parts[2]
            value = parts[3]
            components.append({
                'type': comp_type,
                'name': name,
                'node1': node1,
                'node2': node2,
                'value': value,
                'pins': 2
            })
    
    return components

def build_node_graph(components):
    """ساخت گراف نودها برای ترتیب صحیح رسم"""
    from collections import defaultdict
    
    # نقشه نود به نود (جریان از کجا به کجا می‌رود)
    node_connections = defaultdict(list)
    
    for comp in components:
        if comp['type'] == 'V':
            continue
            
        if comp.get('pins', 2) == 2:
            n1, n2 = comp['node1'], comp['node2']
            # اگر یکی از نودها 0 است، آن طرف زمین است
            if n2 == '0':
                node_connections[n1].append(comp)
            else:
                node_connections[n1].append(comp)
        elif comp['type'] == 'Q':
            # ترانزیستور: کلکتور به امیتر
            node_connections[comp['collector']].append(comp)
        elif comp['type'] == 'M':
            # MOSFET: درین به سورس
            node_connections[comp['drain']].append(comp)
        elif comp['type'] in ['U', 'X']:
            # آپ‌امپ یا IC: ورودی به خروجی
            if 'in_p' in comp:
                node_connections[comp['in_p']].append(comp)
            elif 'all_nodes' in comp and len(comp['all_nodes']) > 0:
                node_connections[comp['all_nodes'][0]].append(comp)
    
    return node_connections
def validate_components(components):
    errors = []
    warnings = []

    for comp in components:
        ctype = comp['type']
        value = comp.get('value', '')

        # --- مقاومت منفی ---
        if ctype == 'R':
            try:
                r = float(value.replace('k','e3').replace('m','e-3'))
                if r <= 0:
                    errors.append(
                        f"❌ مقاومت {comp['name']} مقدار غیرواقعی دارد: {value}"
                    )
            except:
                pass

        # --- خازن الکترولیتی ---
        if ctype == 'C':
            if value.lower().endswith('u') or value.lower().endswith('µ'):
                warnings.append(
                    f"⚠️ خازن {comp['name']} احتمالاً الکترولیتی است؛ پلاریته بررسی نشده"
                )

        # --- اتصال کوتاه ---
        if comp.get('node1') == comp.get('node2'):
            errors.append(
                f"❌ {comp['name']} به یک نود متصل شده (اتصال کوتاه)"
            )

    return errors, warnings

def find_circuit_path(components, start_node='1'):
    """پیدا کردن مسیر مدار از شروع تا پایان"""
    path = []
    visited = set()
    
    # ساخت نقشه نود به قطعات
    node_map = defaultdict(list)
    for comp in components:
        if comp['type'] == 'V':
            continue
        
        if comp.get('pins', 2) == 2 and 'node1' in comp:
            node_map[comp['node1']].append(comp)
        elif comp['type'] == 'Q':
            node_map[comp['collector']].append(comp)
        elif comp['type'] == 'M':
            node_map[comp['drain']].append(comp)
        elif comp['type'] in ['U', 'X']:
            # آپ‌امپ: از ورودی شروع می‌شود
            if 'in_p' in comp:
                node_map[comp['in_p']].append(comp)
            elif 'all_nodes' in comp and len(comp['all_nodes']) > 1:
                node_map[comp['all_nodes'][1]].append(comp)  # ورودی مثبت
    
    # پیمایش از نود شروع
    current_node = start_node
    
    while current_node != '0' and len(path) < 20:
        if current_node not in node_map or not node_map[current_node]:
            break
            
        # پیدا کردن قطعات متصل به این نود
        available_comps = [c for c in node_map[current_node] if c['name'] not in visited]
        
        if not available_comps:
            break
        
        # گروه‌بندی قطعات موازی
        parallel_group = []
        next_node = None
        
        for comp in available_comps:
            if comp.get('pins', 2) == 2 and 'node1' in comp and 'node2' in comp:
                n1, n2 = comp['node1'], comp['node2']
                # تعیین نود بعدی
                if n1 == current_node:
                    comp_next = n2
                else:
                    comp_next = n1
                
                # اگر همه قطعات به یک نود می‌رسند، موازی هستند
                if next_node is None:
                    next_node = comp_next
                
                if comp_next == next_node:
                    parallel_group.append(comp)
                    visited.add(comp['name'])
            elif comp['type'] == 'Q':
                parallel_group.append(comp)
                visited.add(comp['name'])
                next_node = comp['emitter']
            elif comp['type'] == 'M':
                parallel_group.append(comp)
                visited.add(comp['name'])
                next_node = comp['source']
            elif comp['type'] in ['U', 'X']:
                # آپ‌امپ: از خروجی ادامه می‌یابد
                parallel_group.append(comp)
                visited.add(comp['name'])
                if 'out' in comp:
                    next_node = comp['out']
                elif 'all_nodes' in comp and len(comp['all_nodes']) > 0:
                    next_node = comp['all_nodes'][0]  # خروجی
        
        if parallel_group:
            path.append(parallel_group)
        
        current_node = next_node
        
        if current_node is None:
            break
    
    return path

def draw_schematic(netlist_text):
    """تحلیل، اعتبارسنجی و رسم شماتیک مدار"""

    # 1️⃣ پارس نت‌لیست
    components = parse_netlist(netlist_text)
    if not components:
        print("❌ هیچ قطعه‌ای برای رسم یافت نشد.")
        return

    # 2️⃣ اعتبارسنجی
    errors, warnings = validate_components(components)

    if errors:
        print("\n🚨 خطاهای بحرانی مدار:")
        for e in errors:
            print(e)
        print("⛔ رسم شماتیک متوقف شد.")
        return

    if warnings:
        print("\n⚠️ هشدارها:")
        for w in warnings:
            print(w)

    # 3️⃣ رسم شماتیک
    d = schemdraw.Drawing(unit=2.5)

    # پیدا کردن منبع ولتاژ
    voltage_source = next((c for c in components if c['type'] == 'V'), None)
    if not voltage_source:
        print("⚠️ منبع ولتاژ یافت نشد.")
        return

    other_comps = [c for c in components if c['type'] != 'V']

    # پیدا کردن مسیر مدار
    circuit_path = find_circuit_path(other_comps, start_node=voltage_source['node1'])

    # رسم منبع ولتاژ
    v_source = d.add(
        elm.SourceV().up().label(f"{voltage_source['name']}\\n{voltage_source['value']}")
    )
    v_bottom = v_source.start

    d.add(elm.Line().right().length(1))

    MAX_PER_ROW = 3
    row_count = 0

    for group_idx, group in enumerate(circuit_path):
        if row_count >= MAX_PER_ROW and len(circuit_path) - group_idx > 1:
            d.add(elm.Line().down().length(3))
            row_count = 0
            direction = 'left'
        else:
            direction = 'right'

        if len(group) == 1:
            draw_single_component(d, group[0], direction)
        else:
            draw_parallel_group(d, group, direction)

        if group_idx < len(circuit_path) - 1:
            d.add(elm.Line().right().length(0.3) if direction == 'right'
                  else elm.Line().left().length(0.3))

        row_count += 1

    # بستن مدار
    current_pos = d.here
    if abs(current_pos[1] - v_bottom[1]) > 0.1:
        d.add(elm.Line().up().toy(v_bottom[1])
              if current_pos[1] < v_bottom[1]
              else elm.Line().down().toy(v_bottom[1]))

    if abs(current_pos[0] - v_bottom[0]) > 0.1:
        d.add(elm.Line().tox(v_bottom[0]))

    d.draw()
    print("✅ شماتیک مدار رسم شد!")


def draw_single_component(d, comp, direction='right'):
    """رسم یک قطعه منفرد"""
    comp_type = comp['type']
    comp_name = comp['name']
    comp_value = comp['value']
    label = f"{comp_name}\\n{comp_value}"
    
    if comp_type == 'R':
        elm_obj = elm.Resistor()
    elif comp_type == 'C':
        elm_obj = elm.Capacitor()
    elif comp_type == 'L':
        elm_obj = elm.Inductor2()
    elif comp_type == 'D':
        value_lower = comp_value.lower()
        if 'zener' in value_lower:
            elm_obj = elm.Zener()
        else:
            elm_obj = elm.Diode()
    elif comp_type == 'Q':
        elm_obj = elm.BjtNpn()
    elif comp_type == 'M':
        elm_obj = elm.NFet()
    elif comp_type in ['U', 'X']:
        value_lower = comp_value.lower()
        if 'opamp' in value_lower or '741' in value_lower or 'lm' in value_lower or 'tl' in value_lower:
            # آپ‌امپ
            elm_obj = elm.Opamp()
        else:
            # IC - خط ساده با باکس در وسط
            if direction == 'right':
                # خط شروع
                d.add(elm.Line().right().length(0.5))
                box_start_x = d.here[0]
                box_start_y = d.here[1]
                
                # رسم مستطیل با push/pop
                d.push()
                d.add(elm.Line().up().length(0.8))
                d.add(elm.Line().right().length(2))
                d.add(elm.Line().down().length(1.6))
                d.add(elm.Line().left().length(2))
                d.add(elm.Line().up().length(0.8))
                d.pop()
                
                # لیبل در وسط
                d.add(elm.Label().at((box_start_x + 1, box_start_y)).label(label))
                
                # ادامه خط - حرکت دستی
                d.here = (box_start_x + 2, box_start_y)
                d.add(elm.Line().right().length(0.5))
            else:
                # خط شروع
                d.add(elm.Line().left().length(0.5))
                box_start_x = d.here[0]
                box_start_y = d.here[1]
                
                # رسم مستطیل
                d.push()
                d.add(elm.Line().up().length(0.8))
                d.add(elm.Line().left().length(2))
                d.add(elm.Line().down().length(1.6))
                d.add(elm.Line().right().length(2))
                d.add(elm.Line().up().length(0.8))
                d.pop()
                
                # لیبل در وسط
                d.add(elm.Label().at((box_start_x - 1, box_start_y)).label(label))
                
                # ادامه خط
                d.here = (box_start_x - 2, box_start_y)
                d.add(elm.Line().left().length(0.5))
            
            return
    else:
        elm_obj = elm.Resistor()
    
    if direction == 'right':
        d.add(elm_obj.right().label(label))
    else:
        d.add(elm_obj.left().label(label))

def draw_parallel_group(d, group, direction='right'):
    """رسم گروه موازی"""
    start_pos = d.here
    spacing = 2.0
    length = 3.0
    
    # رسم اولین شاخه
    draw_single_component(d, group[0], direction)
    end_pos = d.here
    
    # رسم بقیه شاخه‌ها
    for idx, comp in enumerate(group[1:], start=1):
        d.push()
        d.move_from(start_pos)
        d.add(elm.Line().down().length(spacing * idx))
        draw_single_component(d, comp, direction)
        d.add(elm.Line().up().toy(end_pos[1]))
        d.pop()
    
    d.move_from(end_pos)

# --- ۳. توابع Save و Load ---

def save_circuit(spice_code, description="", filename=None):
    """ذخیره مدار"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"circuit_{timestamp}.json"
    
    circuit_data = {
        'description': description,
        'spice_code': spice_code,
        'date': datetime.now().isoformat(),
        'version': '3.0'
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(circuit_data, f, ensure_ascii=False, indent=2)
        print(f"✅ مدار در '{filename}' ذخیره شد.")
        return filename
    except Exception as e:
        print(f"❌ خطا در ذخیره: {e}")
        return None

def load_circuit(filename):
    """بارگذاری مدار"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            circuit_data = json.load(f)
        
        print(f"✅ مدار از '{filename}' بارگذاری شد.")
        print(f"📝 توضیحات: {circuit_data.get('description', 'ندارد')}")
        print(f"📅 تاریخ: {circuit_data.get('date', 'نامشخص')}")
        
        return circuit_data['spice_code']
    except FileNotFoundError:
        print(f"❌ فایل '{filename}' یافت نشد.")
        return None
    except Exception as e:
        print(f"❌ خطا در بارگذاری: {e}")
        return None

def list_saved_circuits():
    """لیست مدارهای ذخیره شده"""
    import glob
    circuits = glob.glob("circuit_*.json")
    
    if not circuits:
        print("📁 هیچ مدار ذخیره‌شده‌ای یافت نشد.")
        return []
    
    print("\n📁 مدارهای ذخیره شده:")
    print("-" * 50)
    for i, circuit in enumerate(circuits, 1):
        try:
            with open(circuit, 'r', encoding='utf-8') as f:
                data = json.load(f)
            desc = data.get('description', 'بدون توضیحات')[:30]
            date = data.get('date', 'نامشخص')[:10]
            print(f"{i}. {circuit} - {desc} ({date})")
        except:
            print(f"{i}. {circuit} - خطا در خواندن")
    print("-" * 50)
    
    return circuits

# --- ۴. تابع تشخیص گفتار ---
def get_description_from_voice():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎙️ لطفاً توضیحات مدار را بیان کنید:")
        r.adjust_for_ambient_noise(source)
        try:
            audio = r.listen(source, timeout=10)
            print("... در حال تشخیص گفتار ...")
            text = r.recognize_google(audio, language="fa-IR")
            print(f"✅ تشخیص: {text}")
            return text
        except Exception as e:
            print(f"❌ خطا در تشخیص گفتار: {e}")
            return None

# --- ۵. تولید کد SPICE ---
def generate_spice_code(description):
    """تولید کد SPICE با Gemini"""
    try:
        client = genai.Client()
        prompt = f"""
شما متخصص تحلیل مدار هستید. فقط کد SPICE تولید کنید.

قوانین:
1. فقط کد SPICE خالص
2. نام نودها فقط عدد (0, 1, 2, ...)
3. فرمت‌ها:
   - R<نام> <نود1> <نود2> <مقدار>
   - C<نام> <نود1> <نود2> <مقدار>  
   - L<نام> <نود1> <نود2> <مقدار>
   - V<نام> <نود+> <نود-> <مقدار>
   - D<نام> <آند> <کاتد> <مدل>
   - Q<نام> <کلکتور> <بیس> <امیتر> <مدل>
   - M<نام> <درین> <گیت> <سورس> <بادی> <مدل>

توضیحات: {description}
"""
        print("... درخواست به Gemini ...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        spice_code = response.text.strip()
        spice_code = re.sub(r'```[\s\S]*?```', '', spice_code).strip()
        
        print("\n" + "="*40)
        print("💡 کد SPICE:")
        print("="*40)
        print(spice_code)
        print("="*40)

        return spice_code
    except Exception as e:
        print(f"❌ خطا در تولید: {e}")
        return None

# --- ۶. مثال‌های تستی ---
def get_test_examples():
    return {
        '1': {
            'name': 'مدار سادهی',
            'code': """V1 1 0 12V
R1 1 2 -100
C1 2 0 100u
"""
        },
        '2': {
            'name': 'مدار با ترانزیستور',
            'code': """V1 1 0 5V
R1 1 2 10
Q1 2 3 0 2N2222"""
        },
        '3': {
            'name': 'مدار موازی',
            'code': """V1 1 0 10V
R1 1 2 100
R2 1 2 200
R3 2 0 300"""
        },
        '4': {
            'name': 'مدار با دیود',
            'code': """V1 1 0 12V
R1 1 2 1k
D1 2 3 1N4148
R2 3 0 1k"""
        },
        '5': {
            'name': 'مدار با آپ‌امپ',
            'code': """V1 1 0 12V
R1 1 2 10k
U1 3 2 4 1 0 LM741
R2 3 0 1k"""
        },
        '6': {
            'name': 'مدار با IC 555 (تایمر)',
            'code': """
V1 1 0 9V
R1 1 2 1k
R2 2 3 1k
U1 4 3 2 1 0 555
C1 4 0 10u
R3 4 0 10k"""
        },
        '7': {
            'name': 'مدار با MOSFET',
            'code': """V1 1 0 12V
R1 1 2 100
M1 2 3 0 0 IRF530
R2 3 0 1k"""
        },
        '8': {
            'name': 'مدار پیچیده',
            'code': """V1 1 0 15V
R1 1 2 1k
D1 2 3 1N4007
C1 3 4 100u
U1 5 4 6 1 0 LM741
R2 5 0 2k"""
        }
    }

# --- ۷. تابع اصلی ---
def main():
    print("=" * 60)
    print("🔌 برنامه تولید کد SPICE و شماتیک")
    print("=" * 60)

    while True:
        print("\n📋 منو:")
        print("1️⃣  تولید مدار (متنی)")
        print("2️⃣  تولید مدار (صوتی)")
        print("3️⃣  مثال‌های تستی")
        print("4️⃣  بارگذاری مدار")
        print("5️⃣  لیست مدارها")
        print("0️⃣  خروج")
        print("-" * 60)
        
        choice = input("انتخاب: ").strip()
        
        if choice == '0':
            print("👋 خداحافظ!")
            return
        
        elif choice == '1':
            desc = input("\n📝 توضیحات مدار:\n").strip()
            if desc:
                spice_code = generate_spice_code(desc)
                if spice_code:
                    draw_schematic(spice_code)
                    if input("\n💾 ذخیره؟ (y/n): ").lower() == 'y':
                        save_circuit(spice_code, desc)
        
        elif choice == '2':
            desc = get_description_from_voice()
            if desc:
                spice_code = generate_spice_code(desc)
                if spice_code:
                    draw_schematic(spice_code)
                    if input("\n💾 ذخیره؟ (y/n): ").lower() == 'y':
                        save_circuit(spice_code, desc)
        
        elif choice == '3':
            examples = get_test_examples()
            print("\n🧪 مثال‌ها:")
            for key, ex in examples.items():
                print(f"{key}. {ex['name']}")
            
            test = input("انتخاب: ").strip()
            if test in examples:
                print(f"\n{examples[test]['code']}")
                draw_schematic(examples[test]['code'])
        
        elif choice == '4':
            fname = input("\n📂 نام فایل: ").strip()
            if not fname.endswith('.json'):
                fname += '.json'
            spice_code = load_circuit(fname)
            if spice_code:
                draw_schematic(spice_code)
        
        elif choice == '5':
            circuits = list_saved_circuits()
            if circuits:
                idx = input("\n📂 شماره مدار: ").strip()
                try:
                    spice_code = load_circuit(circuits[int(idx)-1])
                    if spice_code:
                        draw_schematic(spice_code)
                except:
                    pass

if __name__ == "__main__":
    main()