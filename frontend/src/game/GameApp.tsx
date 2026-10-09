import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { GameHeader } from "../components/GameHeader";
import type { FrameProps } from "../components/GameFrame";
import { ServiceBar } from "../components/ServiceBar";
import { forgetToken, rememberToken } from "../lib/storage";
import { useLanguage } from "../lib/language";
import { CorrectScreen } from "../screens/CorrectScreen";
import { CoverScreen } from "../screens/CoverScreen";
import { FinishScreen } from "../screens/FinishScreen";
import { LandmarkScreen } from "../screens/LandmarkScreen";
import { LinkNotValidScreen } from "../screens/LinkNotValidScreen";
import { LoadingScreen } from "../screens/LoadingScreen";
import { PhotoScreen } from "../screens/PhotoScreen";
import { RevealedScreen } from "../screens/RevealedScreen";
import { TaskScreen } from "../screens/TaskScreen";
import { TimesUpScreen } from "../screens/TimesUpScreen";
import { WelcomeScreen } from "../screens/WelcomeScreen";
import { EMPTY_UI, selectScreen, type LocalUi } from "./selectScreen";
import { useGame } from "./useGame";

export function GameApp({ token }: { token: string }) {
  const game = useGame(token);
  const [language, setLanguage] = useLanguage();
  const [ui, setUi] = useState<LocalUi>(EMPTY_UI);
  const kind = game.view.kind;
  const invalidReason = game.view.kind === "invalid" ? game.view.info.reason : null;
  useEffect(() => {
    if (kind === "ready") rememberToken(token);
    // A not-yet-open link will work later ("you won't need a new link"), so "/" should still find it.
    if (invalidReason === "unknown" || invalidReason === "expired") forgetToken(token);
  }, [kind, invalidReason, token]);
  const onTimeUp = useCallback(() => void game.refresh(), [game.refresh]);
  const status = game.view.kind === "ready" ? game.view.state.status : null;
  useEffect(() => {                         // after a reset (R-25) the run restarts at task 1
    if (status === "not_started") setUi(EMPTY_UI);
  }, [status]);

  if (game.view.kind === "loading") return <LoadingScreen offline={game.offline} />;
  if (game.view.kind === "invalid") return <LinkNotValidScreen info={game.view.info} />;

  const { state, receivedAt } = game.view;
  const position = state.position;
  const frame: FrameProps = {
    offline: game.offline, notice: game.notice, onNoticeDone: game.clearNotice,
    header: state.clock && state.phase !== "results"
      ? <GameHeader clock={state.clock} position={position} taskCount={state.game.task_count}
                    receivedAt={receivedAt} onTimeUp={onTimeUp}
                    availableLanguages={state.game.available_languages}
                    language={language}
                    onLanguageChange={setLanguage} />
      : null,
  };
  const ack = () => setUi((u) => ({ ...u, ackedPosition: position }));
  const albumUrl = `/album/${encodeURIComponent(token)}`;   // the memories album (issue #33) uses the same link
  const rate = (stars: number) => void game.act(() => api.rate(token, position, stars));   // issue #38
  const feedback = (text: string) => game.act(() => api.feedback(token, text));

  const screen = renderScreen();
  return (
    <>
      {screen}
      {state.service && <ServiceBar onReset={() => game.act(() => api.reset(token))} />}
    </>
  );

  function renderScreen() {
    switch (selectScreen(state, ui)) {
      case "cover":
        return <CoverScreen state={state} frame={frame} language={language} onLanguageChange={setLanguage}
                        onContinue={() => setUi((u) => ({ ...u, coverSeen: true }))} />;
      case "welcome":
        return <WelcomeScreen state={state} frame={frame} language={language} onLanguageChange={setLanguage}
                              onStart={() => game.act(() => api.start(token))} />;
      case "task":
        return <TaskScreen key={position} state={state} receivedAt={receivedAt} frame={frame} language={language}
                           onAnswer={(a) => game.act(() => api.answer(token, position, a))}
                           onHint={(n) => game.act(() => api.hint(token, position, n))}
                           onCompass={() => game.act(() => api.compass(token))}
                           onReveal={() => game.act(() => api.reveal(token, position))} />;
      case "correct":
        return <CorrectScreen state={state} frame={frame} language={language} onContinue={ack} onRate={rate} />;
      case "revealed":
        return <RevealedScreen state={state} frame={frame} language={language} onContinue={ack} onRate={rate} />;
      case "photo":
        return <PhotoScreen key={position} state={state} frame={frame}
                            upload={(file, onProgress) => game.track(api.uploadPhoto(token, position, file, onProgress))}
                            onFlowStart={() => setUi((u) => ({ ...u, ackedPosition: position, photoFlowPosition: position }))}
                            onUploaded={game.applyResult}
                            onContinue={() => {
                              // R-25: without a photo, service Continue must advance (the upload is
                              // what normally flips the phase); with one, the usual landmark flow.
                              if ((state.task?.photo_count ?? 0) > 0) setUi((u) => ({ ...u, photoFlowPosition: null }));
                              else game.act(() => api.advance(token, position));
                            }}
                            onError={game.fail} />;
      case "landmark":
        return <LandmarkScreen state={state} frame={frame} language={language}
                               onNext={() => game.act(() => api.advance(token, position))} />;
      case "finish":
        return <FinishScreen state={state} frame={frame} albumUrl={albumUrl} onFeedback={feedback} />;
      case "timesup":
        return <TimesUpScreen state={state} frame={frame} albumUrl={albumUrl} onFeedback={feedback} />;
    }
  }
}
