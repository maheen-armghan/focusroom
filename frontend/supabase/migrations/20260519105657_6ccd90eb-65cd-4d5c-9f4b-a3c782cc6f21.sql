
CREATE OR REPLACE FUNCTION public.is_session_participant(_session_id uuid, _user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.session_participants
    WHERE session_id = _session_id
      AND user_id = _user_id
      AND left_at IS NULL
  );
$$;

-- session_participants: drop recursive policy and replace
DROP POLICY IF EXISTS "Participants view fellow participants" ON public.session_participants;
CREATE POLICY "Participants view fellow participants"
ON public.session_participants
FOR SELECT
TO authenticated
USING (
  public.is_session_participant(session_id, auth.uid())
  OR EXISTS (
    SELECT 1 FROM public.sessions s
    WHERE s.id = session_participants.session_id AND s.host_id = auth.uid()
  )
);

-- chat_messages
DROP POLICY IF EXISTS "Participants view chat" ON public.chat_messages;
CREATE POLICY "Participants view chat"
ON public.chat_messages
FOR SELECT
TO authenticated
USING (public.is_session_participant(session_id, auth.uid()));

DROP POLICY IF EXISTS "Participants send chat" ON public.chat_messages;
CREATE POLICY "Participants send chat"
ON public.chat_messages
FOR INSERT
TO authenticated
WITH CHECK (
  auth.uid() = user_id
  AND public.is_session_participant(session_id, auth.uid())
);

-- library_files
DROP POLICY IF EXISTS "Users view own files or session files" ON public.library_files;
CREATE POLICY "Users view own files or session files"
ON public.library_files
FOR SELECT
TO authenticated
USING (
  user_id = auth.uid()
  OR (session_id IS NOT NULL AND public.is_session_participant(session_id, auth.uid()))
);

-- tasks
DROP POLICY IF EXISTS "Users view own personal tasks or any session task they particip" ON public.tasks;
CREATE POLICY "Users view own personal tasks or session tasks"
ON public.tasks
FOR SELECT
TO authenticated
USING (
  (scope = 'personal' AND user_id = auth.uid())
  OR (scope = 'session' AND session_id IS NOT NULL AND public.is_session_participant(session_id, auth.uid()))
);
