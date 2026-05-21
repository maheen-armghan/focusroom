
-- Profiles
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username TEXT UNIQUE NOT NULL,
  display_name TEXT,
  bio TEXT,
  avatar_config JSONB NOT NULL DEFAULT '{"hair":"short","skin":"#f5d6b8","outfit":"hoodie","accessory":"none","color":"#7c9eff"}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Profiles are viewable by everyone" ON public.profiles FOR SELECT USING (true);
CREATE POLICY "Users update own profile" ON public.profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users insert own profile" ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.profiles (id, username, display_name)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'username', 'user_' || substr(NEW.id::text, 1, 8)),
    COALESCE(NEW.raw_user_meta_data->>'display_name', NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1))
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;
CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- updated_at helper
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
CREATE TRIGGER trg_profiles_updated BEFORE UPDATE ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Sessions (study rooms)
CREATE TYPE public.room_space AS ENUM ('cafe','library','garden','dorm','train');
CREATE TYPE public.session_status AS ENUM ('waiting','active','completed');

CREATE TABLE public.sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT UNIQUE NOT NULL,
  host_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  space public.room_space NOT NULL,
  duration_seconds INT NOT NULL CHECK (duration_seconds BETWEEN 30 AND 10800),
  status public.session_status NOT NULL DEFAULT 'waiting',
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anyone authenticated can view sessions by code" ON public.sessions FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users create sessions" ON public.sessions FOR INSERT TO authenticated WITH CHECK (auth.uid() = host_id);
CREATE POLICY "Host updates session" ON public.sessions FOR UPDATE TO authenticated USING (auth.uid() = host_id);

-- Participants
CREATE TABLE public.session_participants (
  session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  chair_index INT,
  joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  left_at TIMESTAMPTZ,
  avg_focus_score NUMERIC,
  PRIMARY KEY (session_id, user_id)
);
ALTER TABLE public.session_participants ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Participants view fellow participants" ON public.session_participants FOR SELECT TO authenticated USING (
  EXISTS (SELECT 1 FROM public.session_participants sp WHERE sp.session_id = session_participants.session_id AND sp.user_id = auth.uid())
  OR EXISTS (SELECT 1 FROM public.sessions s WHERE s.id = session_id AND s.host_id = auth.uid())
);
CREATE POLICY "Users join sessions" ON public.session_participants FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users update own participation" ON public.session_participants FOR UPDATE TO authenticated USING (auth.uid() = user_id);

-- Focus samples
CREATE TABLE public.focus_samples (
  id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  score INT NOT NULL CHECK (score BETWEEN 0 AND 100),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.focus_samples ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users view own focus samples" ON public.focus_samples FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users insert own focus samples" ON public.focus_samples FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- Tasks
CREATE TYPE public.task_scope AS ENUM ('session','personal');
CREATE TABLE public.tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id UUID REFERENCES public.sessions(id) ON DELETE SET NULL,
  scope public.task_scope NOT NULL DEFAULT 'personal',
  title TEXT NOT NULL,
  done BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users view own personal tasks or any session task they participated in" ON public.tasks FOR SELECT TO authenticated USING (
  (scope = 'personal' AND user_id = auth.uid())
  OR (scope = 'session' AND session_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.session_participants sp WHERE sp.session_id = tasks.session_id AND sp.user_id = auth.uid()
  ))
);
CREATE POLICY "Users insert tasks" ON public.tasks FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users update own tasks" ON public.tasks FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users delete own tasks" ON public.tasks FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- Chat messages
CREATE TABLE public.chat_messages (
  id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Participants view chat" ON public.chat_messages FOR SELECT TO authenticated USING (
  EXISTS (SELECT 1 FROM public.session_participants sp WHERE sp.session_id = chat_messages.session_id AND sp.user_id = auth.uid())
);
CREATE POLICY "Participants send chat" ON public.chat_messages FOR INSERT TO authenticated WITH CHECK (
  auth.uid() = user_id AND EXISTS (
    SELECT 1 FROM public.session_participants sp WHERE sp.session_id = chat_messages.session_id AND sp.user_id = auth.uid()
  )
);

-- Library files (metadata; objects in storage)
CREATE TABLE public.library_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES public.sessions(id) ON DELETE SET NULL,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  storage_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  mime_type TEXT,
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '24 hours'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.library_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users view own files or session files" ON public.library_files FOR SELECT TO authenticated USING (
  user_id = auth.uid()
  OR (session_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.session_participants sp WHERE sp.session_id = library_files.session_id AND sp.user_id = auth.uid()
  ))
);
CREATE POLICY "Users upload files" ON public.library_files FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users delete own files" ON public.library_files FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- Storage bucket
INSERT INTO storage.buckets (id, name, public) VALUES ('library', 'library', false);
CREATE POLICY "Users read own library or session library" ON storage.objects FOR SELECT TO authenticated USING (
  bucket_id = 'library' AND (
    (storage.foldername(name))[1] = auth.uid()::text
    OR EXISTS (
      SELECT 1 FROM public.library_files lf
      JOIN public.session_participants sp ON sp.session_id = lf.session_id
      WHERE lf.storage_path = name AND sp.user_id = auth.uid()
    )
  )
);
CREATE POLICY "Users upload to own folder" ON storage.objects FOR INSERT TO authenticated WITH CHECK (
  bucket_id = 'library' AND (storage.foldername(name))[1] = auth.uid()::text
);
CREATE POLICY "Users delete own files" ON storage.objects FOR DELETE TO authenticated USING (
  bucket_id = 'library' AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE public.chat_messages;
ALTER PUBLICATION supabase_realtime ADD TABLE public.session_participants;
ALTER PUBLICATION supabase_realtime ADD TABLE public.tasks;
