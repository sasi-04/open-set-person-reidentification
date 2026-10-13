/**
 * The re-identification workspace state machine.
 *
 * In plain words: this hook holds everything the workspace screen needs - the chosen
 * image, the people found in it, which one is selected, and the result - and exposes
 * plain actions ("choose file", "detect", "run", "reset"). The screen itself only draws.
 *
 * Which matching mode is used (decided here, in one place):
 *   - "image is already a person crop" ticked    -> mode "crop"  (no detector)
 *   - "match everyone" ticked                    -> mode "all"   (server detects and matches each person)
 *   - a person was selected after "Detect"       -> mode "box"   (only that person)
 *   - otherwise                                  -> mode "all"
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";
import type { Detection, PersonResult, PredictResponse } from "@/types/api";

export interface ChosenImage {
  file: File;
  url: string; // object URL for the preview
}

export function useReid() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [image, setImage] = useState<ChosenImage | null>(null);
  const [asCrop, setAsCrop] = useState(false);
  const [matchAll, setMatchAll] = useState(false);
  const [detections, setDetections] = useState<Detection[] | null>(null);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [selected, setSelected] = useState<number | null>(null); // index within `detections`
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [activePerson, setActivePerson] = useState(0); // which result person the right-hand panels show
  const [error, setError] = useState<string | null>(null);

  // Free the preview URL when the image is replaced or the screen closes.
  useEffect(() => () => {
    if (image) URL.revokeObjectURL(image.url);
  }, [image]);

  /** Start a fresh query but keep the processing options the person already chose. */
  const newQuery = useCallback(() => {
    setImage(null);
    setDetections(null);
    setImageSize(null);
    setSelected(null);
    setResult(null);
    setActivePerson(0);
    setError(null);
  }, []);

  /** Clear everything, including the options. */
  const reset = useCallback(() => {
    newQuery();
    setAsCrop(false);
    setMatchAll(false);
  }, [newQuery]);

  const chooseFile = useCallback((file: File) => {
    setImage({ file, url: URL.createObjectURL(file) });
    setDetections(null);
    setImageSize(null);
    setSelected(null);
    setResult(null);
    setActivePerson(0);
    setError(null);
  }, []);

  const detect = useMutation({
    mutationFn: (file: File) => api.detect(file),
    onMutate: () => setError(null),
    onSuccess: (response) => {
      setDetections(response.detections);
      setImageSize(response.image);
      setSelected(response.detections.length ? 0 : null);
      setResult(null);
      if (!response.detections.length) {
        setError("No person was detected in this image. Try a clearer photo, or tick “Image is already a person crop”.");
      } else {
        toast.success(`${response.detections.length} ${response.detections.length === 1 ? "person" : "people"} detected.`);
      }
    },
    onError: (failure) => setError(describeError(failure)),
  });

  const mode: "crop" | "box" | "all" = asCrop ? "crop" : matchAll ? "all" : detections?.length && selected !== null ? "box" : "all";

  const predict = useMutation({
    mutationFn: ({ file }: { file: File }) => {
      const box = mode === "box" && detections && selected !== null ? detections[selected].box : undefined;
      return api.predict(file, { mode, box, topK: 5 });
    },
    onMutate: () => {
      setError(null);
      setResult(null);
    },
    onSuccess: (response) => {
      setResult(response);
      setActivePerson(0);
      setImageSize(response.image);
      // A request that detected people itself also tells us where they are.
      if (response.mode === "all") {
        setDetections(
          response.people
            .filter((p) => p.box)
            .map((p) => ({ index: p.index, box: p.box as number[], detector_score: p.detector_score ?? 0, quality: p.quality as Detection["quality"] })),
        );
      }
      void queryClient.invalidateQueries({ queryKey: keys.overview });
      void queryClient.invalidateQueries({ queryKey: keys.history });
    },
    onError: (failure) => setError(describeError(failure)),
  });

  // The person whose decision and candidates are shown.
  const person: PersonResult | null = result?.people[activePerson] ?? null;

  // Where to draw the box for each result person (mode "box" results do not repeat the box of "detections").
  const boxFor = useMemo(() => {
    return (personIndex: number): number[] | null => {
      const fromResult = result?.people[personIndex]?.box;
      if (fromResult) return fromResult;
      if (result?.mode === "box" && detections && selected !== null) return detections[selected].box;
      return null;
    };
  }, [result, detections, selected]);

  return {
    image, chooseFile, reset, newQuery,
    asCrop, setAsCrop, matchAll, setMatchAll,
    detections, imageSize, selected, setSelected,
    detect: () => image && detect.mutate(image.file),
    run: () => image && predict.mutate({ file: image.file }),
    detecting: detect.isPending,
    matching: predict.isPending,
    mode,
    result, person, activePerson, setActivePerson, boxFor,
    error,
  };
}
