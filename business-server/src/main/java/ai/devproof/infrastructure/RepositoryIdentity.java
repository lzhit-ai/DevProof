package ai.devproof.infrastructure;

import java.net.URI;
import java.util.*;

/** Identity comparison only; remote access policy remains with the caller. */
public final class RepositoryIdentity {
    private RepositoryIdentity() {}
    public static boolean githubMatches(String raw,String slug) {
        String identity=githubSlug(raw);
        return identity!=null && identity.equals(UnicodeText.casefold(UnicodeText.strip(slug).replaceAll("^/+|/+$","")));
    }
    public static String githubSlug(String raw) {
        try {
            URI uri=URI.create(UnicodeText.strip(raw));
            if((!"https".equalsIgnoreCase(uri.getScheme()) && !"ssh".equalsIgnoreCase(uri.getScheme())) || !"github.com".equalsIgnoreCase(uri.getHost()))return null;
            List<String> parts=Arrays.stream(uri.getRawPath().split("/")).filter(s->!s.isEmpty()).toList();
            if(parts.size()!=2)return null;
            String name=parts.get(1); if(name.endsWith(".git"))name=name.substring(0,name.length()-4);
            return name.isEmpty()?null:UnicodeText.casefold(parts.getFirst()+"/"+name);
        } catch(RuntimeException e) { return null; }
    }
}
