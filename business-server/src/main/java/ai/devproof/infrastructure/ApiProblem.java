package ai.devproof.infrastructure;

public class ApiProblem extends RuntimeException {
    public final int status;
    public final String code;
    public ApiProblem(int status, String code, String message) {
        super(message); this.status = status; this.code = code;
    }
}
