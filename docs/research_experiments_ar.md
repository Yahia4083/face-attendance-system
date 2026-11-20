# دليل تجارب الورقة البحثية

هذا البروتوكول يختبر شيئين منفصلين:

1. التعرف على الوجه باستخدام MTCNN وFaceNet وسياسة المطابقة الحالية.
2. التحقق النشط من الحيوية باستخدام تحدي تحريك الرأس يسارًا أو يمينًا.

أداة التجربة لا تستدعي مسار الحضور، ولذلك لا تنشئ Check-in أو Check-out ولا
تغير أي سجل حضور. وهي لا تحفظ الصور افتراضيًا؛ الخيار `--save-frames` يحفظها
محليًا فقط داخل `storage/evaluation/`، وهو مسار مستبعد من Git.

## 1. التحضير قبل جمع البيانات

- احصل على موافقة المشاركين على جمع صور الوجه واستخدامها في التقييم المحلي.
- أعط كل مشارك رمزًا مثل `P01` و`P02`، وكل شخص غير مسجل رمزًا مثل `U01`.
- احتفظ بجدول الربط بين الرمز والهوية الحقيقية في ملف خاص منفصل.
- ثبّت الكاميرا والدقة وإعدادات الدوران والانعكاس طوال التجربة.
- ضع علامات ثابتة لمسافتي `near` و`far` وسجل وصف الإضاءة المستخدمة.
- ثبّت عتبة التعرف وإعدادات المعالجة قبل رؤية النتائج، ولا تعدّلها أثناء جمع الاختبار.
- اجمع صور Enrollment أولًا، ثم اجمع Probe في جلسة لاحقة. لا تستخدم صورة
  Enrollment نفسها كصورة اختبار.

الحد الأدنى المقترح:

- من 10 إلى 20 مشاركًا مسجلًا.
- خمس صور Enrollment متنوعة لكل مشارك.
- خمس محاولات مستقلة لكل شرط إلزامي ولكل مشارك.
- خمسة أشخاص غير مسجلين على الأقل، بعشر محاولات لكل شخص.
- عشرون محاولة على الأقل لكل سيناريو من سيناريوهات الحيوية النشطة.

الشروط الإلزامية للتعرف هي: `frontal`، و`pose_left`، و`pose_right`،
و`different_lighting`، و`near`، و`far`. ويمكن إضافة `glasses` و`hairstyle`
للمشاركين الذين تنطبق عليهم هذه الحالات.

## 2. تجهيز البيئة والكاميرا

شغّل PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
$env:MOBILE_CAMERA_SOURCE="0"
$env:LIVE_CAMERA_FLIP="0"
$env:LIVE_CAMERA_ROTATE="0"
$env:LIVE_ATTENDANCE_WORKER_FRAME_COUNT="8"
$env:LIVE_ATTENDANCE_WORKER_CAPTURE_SECONDS="3"
python tools\check_live_attendance_readiness.py
```

لا تبدأ جمع البيانات إلا إذا كانت الكاميرا وMTCNN وFaceNet وخدمة التحدي النشط
جاهزة. أثناء أداة التجربة: `SPACE` يبدأ المحاولة و`Q` ينهي الجلسة.

إذا ظهر `no valid frame` مع كاميرا Camo، افتح تطبيق Camo ووصل الهاتف واجعل
المعاينة الحية ظاهرة، ثم أغلق أي برنامج آخر يستخدم الكاميرا وأعد فحص الجاهزية.
فتح جهاز الكاميرا وحده لا يكفي إذا كان Camo يعرض شاشة انتظار رمادية أو سوداء.
أداة التجارب تعيد الاتصال تلقائيًا كل ثانيتين إذا انقطع بث Camo، كما تنتظر
ثانيتين بين شروط الاختبار حتى يحرر Windows جهاز الكاميرا. إذا كانت نافذة قديمة
تعرض `Camera unavailable`، اضغط `Q` ثم أعد أمر الشخص نفسه؛ المحاولات المحفوظة
لن تتكرر.

اختبار التعرف يقرأ الموظفين وFaceNet embeddings من MySQL، لذلك تحقق أيضًا من
أن المنفذ `3306` يعمل قبل تشغيله:

```powershell
Test-NetConnection 127.0.0.1 -Port 3306
```

إذا كانت `TcpTestSucceeded` تساوي `False`، شغّل MySQL ثم أعد الأمر. اختبار
الحيوية وحده لا يحتاج إلى قاعدة البيانات.

## 3. صور Enrollment

أنشئ الموظفين المشاركين من واجهة النظام وسجل خمس صور جيدة لكل شخص. اجعل الصور
متنوعة قليلًا في التعبير والزاوية، ولكنها واضحة ومقبولة من فحوص الجودة. بعد
انتهاء Enrollment لا تضف صور Probe إلى معرض الشخص ولا تعيد Enrollment حتى
تنتهي جميع التجارب.

دوّن رقم الموظف الذي يستخدمه النظام، مثل `P02`. هذا الرقم هو القيمة التي
تمررها إلى `--expected-employee-number`.

## 4. اختبار التعرف على الوجه

مثال لخمس محاولات أمامية للمشارك `P01` الذي رقم موظفه `DEMO001`:

```powershell
python tools\run_biometric_experiments.py recognition `
  --participant-id P01 `
  --expected-employee-number DEMO001 `
  --condition frontal `
  --attempts 5 `
  --save-frames
```

كرر الأمر مع تغيير `--condition`:

```text
pose_left
pose_right
different_lighting
near
far
glasses
hairstyle
```

غيّر المشارك ورقم الموظف لكل شخص. نفّذ كل محاولة كالتقاط مستقل: ارجع إلى الوضع
الطبيعي، جهز الشرط من جديد، ثم اضغط `SPACE`. لا تلتقط خمس صور متطابقة من دون
إعادة تموضع الشخص.

### اختبار الشخص غير المسجل

الشخص غير المسجل بيومتريًا لا تُلتقط له صور Enrollment ولا تكون له أي بصمة
وجه نشطة، حتى لو كان له صف إداري محجوز في النظام:

```powershell
python tools\run_biometric_experiments.py recognition `
  --participant-id U01 `
  --expected-employee-number UNKNOWN `
  --condition unknown `
  --attempts 10 `
  --save-frames
```

كرر ذلك لباقي المشاركين غير المسجلين. في نظام التعرف واحد-إلى-متعدد، هذه
هي تجربة Impostor التشغيلية: الشخص غير المسجل يقارن تلقائيًا مع معرض جميع
الموظفين. إذا قُبل كأي موظف فهي `FALSE_ACCEPT`، وإذا رُفض فهي `TRUE_REJECT`.

أما محاولة الموظف المسجل فهي Genuine. قبول الهوية الصحيحة هو `TRUE_ACCEPT`،
ورفضها هو `FALSE_REJECT`. إذا قُبل الموظف المسجل باسم موظف آخر تسجل الأداة
الحالة `MISIDENTIFICATION` وتحسبها فشلًا في التعرف الصحيح، مع إبقائها ظاهرة
بشكل مستقل في التقرير.

## 5. اختبار الحيوية النشطة بصورة منفصلة

لا تختبر التعرف في هذه المرحلة. الهدف هو قرار تحدي الرأس وحده. تستخدم الأداة
تحديًا عشوائيًا يسارًا أو يمينًا لكل محاولة، وبنفس إعداد التشغيل: ثمانية إطارات
خلال ثلاث ثوانٍ.

### شخص حقيقي ينفذ الاتجاه الصحيح

```powershell
python tools\run_biometric_experiments.py liveness `
  --participant-id P01 `
  --scenario correct `
  --attempts 20 `
  --challenge auto `
  --frames 8 `
  --seconds 3 `
  --save-frames
```

### شخص حقيقي يتعمد تنفيذ الاتجاه المعاكس

```powershell
python tools\run_biometric_experiments.py liveness `
  --participant-id P01 `
  --scenario wrong_direction `
  --attempts 20 `
  --challenge auto `
  --frames 8 `
  --seconds 3 `
  --save-frames
```

### شخص حقيقي لا يتحرك

```powershell
python tools\run_biometric_experiments.py liveness `
  --participant-id P01 `
  --scenario no_movement `
  --attempts 20 `
  --challenge auto `
  --frames 8 `
  --seconds 3 `
  --save-frames
```

### صورة ثابتة معروضة على هاتف

اعرض صورة واضحة لشخص مسجل بملء شاشة الهاتف، واجعل كاميرا النظام ترى الهاتف
نفسه لا ملف الصورة الأصلي. غيّر المسافة والزاوية وسطوع الشاشة بين المحاولات
وسجل هذه التفاصيل في `--notes`. أبقِ الهاتف ثابتًا أثناء كل محاولة:

```powershell
python tools\run_biometric_experiments.py liveness `
  --participant-id P01-PHOTO `
  --scenario phone_photo `
  --attempts 20 `
  --challenge auto `
  --frames 8 `
  --seconds 3 `
  --save-frames `
  --notes "Phone model, brightness, distance, and angle"
```

لا تفترض أن صورة الهاتف ستُرفض. النتيجة المسجلة، نجاحًا أو فشلًا، هي التي تدخل
الورقة. والأفضل توزيع العشرين محاولة في كل سيناريو على أربعة أو خمسة مشاركين
بدل تنفيذها كلها على شخص واحد.

## 6. ملف البيانات الناتج

تضاف كل محاولة مباشرة إلى:

```text
storage/evaluation/active_experiments/attempts.csv
```

ويحتوي السجل على Expected identity وPredicted identity ودرجتي أفضل وثاني أفضل
مطابقة وقرار القبول والشرط وقرار الحيوية وسبب الرفض وعدد الإطارات وزمن الالتقاط
وزمن المعالجة والزمن الكلي. إذا استخدمت `--save-frames` تحفظ الإطارات في مجلد
خاص يحمل `attempt_id` نفسه.

خذ نسخة احتياطية خاصة من ملف CSV ومجلد الإطارات بعد كل جلسة. لا ترسلهما إلى
Git ولا تضع الصور أو جدول ربط الهويات في مستودع عام.

## 7. حساب النتائج تلقائيًا

بعد جمع المحاولات:

```powershell
python tools\summarize_biometric_experiments.py
```

ينتج الملفان:

```text
storage/evaluation/active_experiments/summary.json
storage/evaluation/active_experiments/summary.md
```

يشمل التقرير:

- True Accept Rate وFalse Reject Rate للمحاولات المسجلة.
- True Reject Rate وFalse Accept Rate للأشخاص غير المسجلين.
- دقة القرار الكلية، وعدد أخطاء الهوية، وFailure to Acquire.
- المتوسط والوسيط وP95 لزمن التعرف.
- Pass وReject لكل سيناريو حيوية.
- Liveness Success Rate للاتجاه الصحيح.
- Attack Rejection Rate للاتجاه الخاطئ وعدم الحركة وصورة الهاتف.
- فاصل Wilson بنسبة 95% لكل معدل، مع البسط والمقام.

## 8. قواعد تمنع نتائج مضللة

- لا تخلط صور Enrollment بصور Probe.
- لا تحذف المحاولة الصعبة لأنها خفضت النتيجة؛ سجل سبب استبعاد تقني واضح فقط.
- أبلغ عن Failure to Acquire منفصلًا بدل حذف الصور التي لم يكتشف فيها وجه.
- لا تغيّر العتبة بعد رؤية نتائج الاختبار. إذا تغيرت، اجمع مجموعة اختبار جديدة.
- لا تكتب أن معدل الخطأ السكاني صفر لمجرد عدم ظهور خطأ في عينة صغيرة؛ أبلغ عن
  العدد وفاصل الثقة.
- اختبر التعرف والحيوية منفصلين أولًا، ثم يمكن إضافة اختبار كامل لمسار الحضور
  بوصفه تحققًا وظيفيًا لا بديلًا عن القياسين السابقين.
