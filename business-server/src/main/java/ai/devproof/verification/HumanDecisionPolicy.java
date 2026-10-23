package ai.devproof.verification;

import java.util.*;

/** Ordered read options and write validation share the same decision authority. */
public final class HumanDecisionPolicy {
    private static final Map<String,List<String>> OPTIONS=Map.of(
        "SUPPORTED",List.of("CONFIRM_SUPPORT","CONFIRM_PARTIAL","CONFIRM_INSUFFICIENT"),
        "PARTIALLY_SUPPORTED",List.of("CONFIRM_SUPPORT","CONFIRM_PARTIAL","CONFIRM_INSUFFICIENT"),
        "NOT_PROVEN",List.of("CONFIRM_INSUFFICIENT","RETURN_FOR_EVIDENCE"),
        "NOT_ANALYZED",List.of("RETURN_FOR_EVIDENCE"),"CONFLICTING",List.of("RETURN_FOR_EVIDENCE"),"CONFLICT",List.of("RETURN_FOR_EVIDENCE"));
    private HumanDecisionPolicy() {}
    public static List<String> options(String status) { return OPTIONS.getOrDefault(status,List.of()); }
    public static boolean permits(String status,String decision) { return options(status).contains(decision); }
}
