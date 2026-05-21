
CREATE TABLE public.chat_reactions (
  id BIGSERIAL PRIMARY KEY,
  message_id BIGINT NOT NULL REFERENCES public.chat_messages(id) ON DELETE CASCADE,
  session_id UUID NOT NULL,
  user_id UUID NOT NULL,
  emoji TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (message_id, user_id, emoji)
);

CREATE INDEX idx_chat_reactions_message ON public.chat_reactions(message_id);
CREATE INDEX idx_chat_reactions_session ON public.chat_reactions(session_id);

ALTER TABLE public.chat_reactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Participants view reactions"
  ON public.chat_reactions FOR SELECT TO authenticated
  USING (public.is_session_participant(session_id, auth.uid()));

CREATE POLICY "Participants add own reactions"
  ON public.chat_reactions FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id AND public.is_session_participant(session_id, auth.uid()));

CREATE POLICY "Users remove own reactions"
  ON public.chat_reactions FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

ALTER PUBLICATION supabase_realtime ADD TABLE public.chat_reactions;
ALTER TABLE public.chat_reactions REPLICA IDENTITY FULL;
