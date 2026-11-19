// Deliberately vulnerable test app for the lab (SQL built by string concatenation, file path from a parameter).
// Never expose it outside the lab network.
package vulnapp;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

public class App {
  static final String DB = "jdbc:h2:mem:vuln;DB_CLOSE_DELAY=-1";
  static final String FILES = "/tmp/files";

  static void init() throws Exception {
    new File(FILES).mkdirs();
    try (FileWriter w = new FileWriter(FILES + "/hello.txt")) { w.write("hello\n"); }
    try (Connection c = DriverManager.getConnection(DB); Statement s = c.createStatement()) {
      s.execute("CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(20))");
      s.execute("INSERT INTO users VALUES (1,'alice'),(2,'bob'),(3,'carol')");
    }
  }

  static String rows(ResultSet rs) throws Exception {
    StringBuilder b = new StringBuilder("{\"rows\":[");
    boolean first = true;
    while (rs.next()) {
      if (!first) b.append(',');
      first = false;
      b.append('[').append(rs.getObject(1)).append(",\"").append(rs.getObject(2)).append("\"]");
    }
    return b.append("]}").toString();
  }

  public static class Health extends HttpServlet {
    @Override protected void doGet(HttpServletRequest q, HttpServletResponse r) throws IOException {
      r.getWriter().write("ok");
    }
  }

  public static class User extends HttpServlet {
    @Override protected void doGet(HttpServletRequest q, HttpServletResponse r) throws IOException {
      String uid = q.getParameter("id");
      try (Connection c = DriverManager.getConnection(DB); Statement s = c.createStatement()) {
        r.getWriter().write(rows(s.executeQuery("SELECT id, name FROM users WHERE id = " + uid)));
      } catch (Exception e) { r.setStatus(500); r.getWriter().write(e.getClass().getSimpleName()); }
    }
  }

  public static class UserSafe extends HttpServlet {
    @Override protected void doGet(HttpServletRequest q, HttpServletResponse r) throws IOException {
      String uid = q.getParameter("id");
      try (Connection c = DriverManager.getConnection(DB);
           PreparedStatement s = c.prepareStatement("SELECT id, name FROM users WHERE CAST(id AS VARCHAR) = ?")) {
        s.setString(1, uid);
        r.getWriter().write(rows(s.executeQuery()));
      } catch (Exception e) { r.setStatus(500); r.getWriter().write(e.getClass().getSimpleName()); }
    }
  }

  public static class FileRead extends HttpServlet {
    @Override protected void doGet(HttpServletRequest q, HttpServletResponse r) throws IOException {
      String name = q.getParameter("name");
      String p = name.startsWith("/") ? name : FILES + "/" + name;
      try (InputStream in = new FileInputStream(p)) {
        r.getWriter().write(new String(in.readAllBytes()));
      } catch (IOException e) { r.setStatus(500); r.getWriter().write(e.getClass().getSimpleName()); }
    }
  }

  public static void main(String[] a) throws Exception {
    init();
    Tomcat t = new Tomcat();
    t.setPort(8080);
    t.getConnector();
    Context ctx = t.addContext("", new File("/tmp").getAbsolutePath());
    Tomcat.addServlet(ctx, "health", new Health()); ctx.addServletMappingDecoded("/health", "health");
    Tomcat.addServlet(ctx, "user", new User()); ctx.addServletMappingDecoded("/user", "user");
    Tomcat.addServlet(ctx, "usersafe", new UserSafe()); ctx.addServletMappingDecoded("/user_safe", "usersafe");
    Tomcat.addServlet(ctx, "file", new FileRead()); ctx.addServletMappingDecoded("/file", "file");
    t.start();
    t.getServer().await();
  }
}
