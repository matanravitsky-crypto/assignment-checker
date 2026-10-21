// חיבור האתר למסד הנתונים המשותף ב-Supabase.
//
// מי שממלא את הקובץ הזה: כל חבר צוות עם הרשאת כתיבה בריפו, אחרי שהקים פרויקט
// ב-Supabase לפי המדריך באתר (#/setup) או לפי SETUP.md.
//
// supabaseUrl      ה-Project URL מ-Supabase → Project Settings → API Keys / Data API
// supabaseAnonKey  ה-Publishable key (מתחיל ב-sb_publishable_) או ה-anon public key הישן
//
// שני הערכים ציבוריים בכוונה, ומותר שיופיעו בקוד: ההגנה על הנתונים היא בהרשאות שבמסד
// (supabase/schema.sql), ורק מי שברשימת הצוות יכול לקרוא או לכתוב.
// אסור לשים כאן את ה-secret / service_role key או את סיסמת המסד.
//
// כשהערכים ריקים, האתר עובד במצב הדגמה בלבד.
window.APP_CONFIG = {
  repo: "matanravitsky-crypto/assignment-checker",
  supabaseUrl: "",
  supabaseAnonKey: "",
};
